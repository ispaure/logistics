// Opus is linked into VLCKit even when its libavcodec decoder is omitted.
#import <libavcodec/avcodec.h>
#import <libavutil/channel_layout.h>

typedef struct OpusMSDecoder OpusMSDecoder;
extern OpusMSDecoder *opus_multistream_decoder_create(int32_t rate, int channels,
    int streams, int coupled, const unsigned char *mapping, int *error);
extern int opus_multistream_decode_float(OpusMSDecoder *decoder, const unsigned char *data,
    int32_t length, float *pcm, int frameSize, int fec);
extern void opus_multistream_decoder_destroy(OpusMSDecoder *decoder);

typedef struct {
    OpusMSDecoder *decoder;
    AVCodecContext *encoder;
    AVFrame *frame;
    AVPacket *packet;
    float *pcm;
    int channels, used;
    double gain;
    int64_t first, end, cursor, inputCursor;
    const uint8_t *order;
} LGMKVOpus;

static const AVRational LGOpusClock = {1, 48000};

static void LGOpusClose(LGMKVOpus *audio) {
    if (audio->decoder) opus_multistream_decoder_destroy(audio->decoder);
    avcodec_free_context(&audio->encoder);
    av_frame_free(&audio->frame);
    av_packet_free(&audio->packet);
    av_freep(&audio->pcm);
}

static BOOL LGOpusOpen(LGMKVOpus *audio, AVCodecParameters *input, AVStream *output,
                       int64_t start, int64_t end) {
    const uint8_t *head = input->extradata;
    int channels = input->ch_layout.nb_channels;
    static const uint8_t stereo[] = {0, 1};
    static const uint8_t surround[] = {0, 2, 1, 5, 3, 4}; // Vorbis to FFmpeg 5.1 order.
    if (!head || input->extradata_size < 19 || memcmp(head, "OpusHead", 8) || head[8] != 1 ||
        head[9] != channels || (channels != 1 && channels != 2 && channels != 6)) return NO;
    int family = head[18], streams = 1, coupled = channels == 2;
    const uint8_t *mapping = stereo;
    if (family == 1 && input->extradata_size >= 21 + channels) {
        streams = head[19];
        coupled = head[20];
        mapping = head + 21;
    } else if (family != 0 || channels > 2) {
        return NO;
    }
    if (streams <= 0 || coupled > streams || streams + coupled != channels) return NO;
    for (int channel = 0; channel < channels; channel++) {
        if (mapping[channel] >= channels && mapping[channel] != 255) return NO;
    }
    audio->order = channels == 6 ? surround : stereo;
    audio->channels = channels;
    audio->gain = pow(10.0, (int16_t)AV_RL16(head + 16) / (256.0 * 20.0));
    int error = 0;
    audio->decoder = opus_multistream_decoder_create(48000, channels, streams, coupled, mapping, &error);
    const AVCodec *aac = avcodec_find_encoder_by_name("aac");
    if (!audio->decoder || error || !aac) return NO;
    audio->encoder = avcodec_alloc_context3(aac);
    audio->frame = av_frame_alloc();
    audio->packet = av_packet_alloc();
    audio->pcm = av_malloc_array(5760 * channels, sizeof(float));
    if (!audio->encoder || !audio->frame || !audio->packet || !audio->pcm) return NO;
    AVCodecContext *encoder = audio->encoder;
    encoder->sample_fmt = AV_SAMPLE_FMT_FLTP;
    encoder->sample_rate = 48000;
    encoder->time_base = LGOpusClock;
    encoder->profile = AV_PROFILE_AAC_LOW;
    encoder->bit_rate = channels == 6 ? 320000 : channels == 2 ? 160000 : 96000;
    av_channel_layout_default(&encoder->ch_layout, channels);
    if (avcodec_open2(encoder, aac, NULL) < 0 || encoder->frame_size != 1024 ||
        avcodec_parameters_from_context(output->codecpar, encoder) < 0) return NO;
    output->codecpar->initial_padding = 0; // Encoder priming is discarded at every seek boundary.
    output->time_base = LGOpusClock;
    AVFrame *frame = audio->frame;
    frame->format = encoder->sample_fmt;
    frame->sample_rate = encoder->sample_rate;
    frame->nb_samples = encoder->frame_size;
    if (av_channel_layout_copy(&frame->ch_layout, &encoder->ch_layout) < 0 ||
        av_frame_get_buffer(frame, 0) < 0) return NO;
    audio->first = (start + 1023) / 1024 * 1024;
    audio->end = (end + 1023) / 1024 * 1024;
    // Feed one frame of warmup into the independent AAC encoder. Keep the
    // output on a global sample grid so adjacent fragments join after seeks.
    audio->cursor = audio->first - 1024;
    audio->inputCursor = AV_NOPTS_VALUE;
    return YES;
}

static BOOL LGOpusEncode(LGMKVOpus *audio, AVFormatContext *output, AVFrame *frame, BOOL *wrote) {
    if (avcodec_send_frame(audio->encoder, frame) < 0) return NO;
    int status;
    while ((status = avcodec_receive_packet(audio->encoder, audio->packet)) >= 0) {
        AVPacket *packet = audio->packet;
        if (packet->pts >= audio->first && packet->pts < audio->end) {
            packet->pts += 4800;
            packet->dts += 4800;
            packet->stream_index = 1;
            av_packet_rescale_ts(packet, LGOpusClock, output->streams[1]->time_base);
            if (av_interleaved_write_frame(output, packet) < 0) return NO;
            *wrote = YES;
        }
        av_packet_unref(packet);
    }
    return status == AVERROR(EAGAIN) || status == AVERROR_EOF;
}

static BOOL LGOpusFill(LGMKVOpus *audio, AVFormatContext *output, const float *samples,
                       int64_t until, BOOL *wrote) {
    until = MIN(until, audio->end);
    while (audio->cursor < until) {
        if (audio->used == 0 && av_frame_make_writable(audio->frame) < 0) return NO;
        int count = (int)MIN(until - audio->cursor, 1024 - audio->used);
        for (int channel = 0; channel < audio->channels; channel++) {
            float *plane = (float *)audio->frame->extended_data[channel] + audio->used;
            for (int sample = 0; sample < count; sample++) {
                plane[sample] = samples ? samples[sample * audio->channels + audio->order[channel]] * audio->gain : 0;
            }
        }
        if (samples) samples += count * audio->channels;
        audio->cursor += count;
        audio->used += count;
        if (audio->used == 1024) {
            audio->frame->pts = audio->cursor - 1024;
            if (!LGOpusEncode(audio, output, audio->frame, wrote)) return NO;
            audio->used = 0;
        }
    }
    return YES;
}

static BOOL LGOpusPacket(LGMKVOpus *audio, AVFormatContext *output, AVPacket *packet,
                         AVRational timeBase, BOOL *wrote) {
    int count = opus_multistream_decode_float(audio->decoder, packet->data, packet->size, audio->pcm, 5760, 0);
    if (count <= 0) return NO;
    int64_t start = av_rescale_q(packet->pts, timeBase, LGOpusClock);
    // Matroska's millisecond timestamps round Opus frame boundaries.
    if (audio->inputCursor != AV_NOPTS_VALUE && llabs(start - audio->inputCursor) <= 48) start = audio->inputCursor;
    audio->inputCursor = start + count;
    size_t sideSize = 0;
    const uint8_t *trim = av_packet_get_side_data(packet, AV_PKT_DATA_SKIP_SAMPLES, &sideSize);
    int64_t end = audio->inputCursor;
    if (trim && sideSize >= 8) end -= MIN((uint32_t)count, AV_RL32(trim + 4));
    if (end <= audio->cursor) return YES;
    if (start - audio->cursor > 4800) return NO;
    if (!LGOpusFill(audio, output, NULL, start, wrote)) return NO;
    int64_t skip = MAX(0, audio->cursor - start);
    if (skip >= count) return YES;
    return LGOpusFill(audio, output, audio->pcm + skip * audio->channels, end, wrote);
}
