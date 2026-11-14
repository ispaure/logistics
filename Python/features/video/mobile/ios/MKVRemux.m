// Stream-copy indexed Matroska into independently requested fMP4 fragments.
// The build supplies FFmpeg headers matching the pinned VLCKit binary.
#if __has_include(<libavformat/avformat.h>)
#import <math.h>
#import <libavformat/avformat.h>
#import <libavutil/intreadwrite.h>
#import <libavutil/mem.h>
#import <libavcodec/packet.h>
#import <unistd.h>
#import <fcntl.h>
#import <sys/stat.h>
#import <ifaddrs.h>
#import <arpa/inet.h>
#import <TargetConditionals.h>
#import "MKVOpus.m"

_Static_assert(LIBAVFORMAT_VERSION_INT == AV_VERSION_INT(63, 1, 100),
    "The iOS remux adapter requires the libavformat ABI shipped by pinned VLCKit.");

@interface LGMKVRemux : NSObject
@property(nonatomic, readonly) NSData *initialization;
@property(nonatomic, readonly) NSString *playlist;
- (instancetype)initWithPath:(NSString *)path;
- (NSData *)segment:(NSUInteger)index;
- (NSString *)renditionsJSON;
- (NSData *)fragment:(NSUInteger)index track:(int)track;
- (NSData *)initializationForTrack:(int)track;
- (NSString *)textSegment:(NSUInteger)index track:(int)track;
+ (NSString *)streamAddress;
@end

static const NSUInteger LGMKVMaxFragment = 128 * 1024 * 1024;

static NSDictionary *LGMKVCodecInfo(AVCodecParameters *parameters) {
    // RFC 6381 needs only the configuration record's header, not its SPS/PPS.
    NSUInteger length = parameters->extradata ? MIN(MAX(0, parameters->extradata_size), 32) : 0;
    NSData *configuration = [NSData dataWithBytes:parameters->extradata length:length];
    return @{@"codec": @(avcodec_get_name(parameters->codec_id)),
        @"configuration": [configuration base64EncodedStringWithOptions:0]};
}

typedef struct {
    int fd;
    int64_t bytes, size;
    NSTimeInterval deadline;
    void *output;
} LGMKVIO;

static int LGMKVInterrupt(void *opaque) {
    LGMKVIO *io = opaque;
    return NSProcessInfo.processInfo.systemUptime > io->deadline;
}

static int LGMKVRead(void *opaque, uint8_t *buffer, int count) {
    LGMKVIO *io = opaque;
    if (LGMKVInterrupt(io) || io->bytes > LGMKVMaxFragment * 2) return AVERROR_EXIT;
    ssize_t result = read(io->fd, buffer, count);
    if (result > 0) { io->bytes += result; return (int)result; }
    return result == 0 ? AVERROR_EOF : AVERROR(errno);
}

static int64_t LGMKVSeek(void *opaque, int64_t offset, int whence) {
    LGMKVIO *io = opaque;
    if (LGMKVInterrupt(io)) return AVERROR_EXIT;
    if (whence == AVSEEK_SIZE) return io->size;
    off_t position = lseek(io->fd, offset, whence & ~AVSEEK_FORCE);
    return position < 0 ? AVERROR(errno) : position;
}

static int LGMKVWrite(void *opaque, const uint8_t *buffer, int count) {
    LGMKVIO *io = opaque;
    NSMutableData *output = (__bridge NSMutableData *)io->output;
    if (LGMKVInterrupt(io) || count < 0 || output.length + count > LGMKVMaxFragment) return AVERROR_EXIT;
    [output appendBytes:buffer length:count];
    return count;
}

static void LGMKVFreeIO(AVIOContext **context) {
    if (*context) av_freep(&(*context)->buffer);
    avio_context_free(context);
}

static int LGMKVVideoSync(AVPacket *packet, AVCodecParameters *codec) {
    // Matroska AVC/HEVC packets contain length-prefixed NAL units.
    // HEVC CRA/BLA may have leading pictures. Drop samples before the cue PTS.
    int configurationByte = codec->codec_id == AV_CODEC_ID_H264 ? 4 : 21;
    if (codec->extradata_size <= configurationByte || codec->extradata[0] != 1) return -1;
    unsigned width = (codec->extradata[configurationByte] & 3) + 1;
    const uint8_t *cursor = packet->data, *end = cursor + packet->size;
    while (end - cursor > width) {
        uint32_t length = 0;
        for (unsigned i = 0; i < width; i++) length = (length << 8) | *cursor++;
        if (!length || length > end - cursor) return -1;
        unsigned type = codec->codec_id == AV_CODEC_ID_H264 ? cursor[0] & 31 : (cursor[0] >> 1) & 63;
        if (codec->codec_id == AV_CODEC_ID_H264 ? type == 5 : (type >= 16 && type <= 21)) return (int)type;
        cursor += length;
    }
    return -1;
}

@implementation LGMKVRemux {
    int _file;
    int _video, _audio;
    AVFormatContext *_source;
    AVIOContext *_input;
    LGMKVIO _reader;
    NSArray<NSNumber *> *_starts;
    int64_t _duration;
    NSData *_initialization;
    NSData *_firstFragment;
    NSString *_playlist;
    NSDictionary *_renditions;
}

+ (NSString *)streamAddress {
#if TARGET_OS_SIMULATOR
    return @"127.0.0.1";
#else
    struct ifaddrs *interfaces = NULL;
    if (getifaddrs(&interfaces)) return nil;
    NSString *address = nil;
    for (struct ifaddrs *item = interfaces; item; item = item->ifa_next) {
        if (!item->ifa_addr || item->ifa_addr->sa_family != AF_INET || strcmp(item->ifa_name, "en0")) continue;
        char buffer[INET_ADDRSTRLEN];
        struct sockaddr_in *ip = (struct sockaddr_in *)item->ifa_addr;
        if (inet_ntop(AF_INET, &ip->sin_addr, buffer, sizeof(buffer))) address = @(buffer);
        break;
    }
    freeifaddrs(interfaces);
    return address;
#endif
}

- (instancetype)initWithPath:(NSString *)path {
    self = [super init];
    if (!self) return nil;
    _file = open(path.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    struct stat info;
    if (_file < 0 || fstat(_file, &info) || !S_ISREG(info.st_mode) || info.st_nlink != 1) return nil;
    _reader = (LGMKVIO){.fd = _file, .size = info.st_size,
        .deadline = NSProcessInfo.processInfo.systemUptime + 8};
    uint8_t *buffer = av_malloc(32768);
    if (!buffer) return nil;
    _input = avio_alloc_context(buffer, 32768, 0, &_reader, LGMKVRead, NULL, LGMKVSeek);
    if (!_input) { av_free(buffer); return nil; }
    _source = avformat_alloc_context();
    if (!_source) return nil;
    _source->pb = _input;
    _source->flags |= AVFMT_FLAG_CUSTOM_IO;
    _source->max_index_size = 8 * 1024 * 1024;
    _source->interrupt_callback = (AVIOInterruptCB){LGMKVInterrupt, &_reader};
    const AVInputFormat *matroska = av_find_input_format("matroska");
    if (!matroska || avformat_open_input(&_source, NULL, matroska, NULL) < 0) return nil;
    // Matroska's container header may omit color and cadence carried in HEVC's
    // parameter sets. Resolve those before advertising an HLS variant: Apple
    // rejects an HDR stream labelled SDR, and HDR variants require FRAME-RATE.
    _source->probesize = 4 * 1024 * 1024;
    _source->max_analyze_duration = AV_TIME_BASE;
    if (avformat_find_stream_info(_source, NULL) < 0) return nil;
    _video = av_find_best_stream(_source, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
    if (_video < 0 || _source->duration <= 0 || _source->duration > INT64_C(12) * 3600 * AV_TIME_BASE) return nil;
    AVStream *video = _source->streams[_video];
    if ((video->disposition & AV_DISPOSITION_ATTACHED_PIC) ||
        video->time_base.num <= 0 || video->time_base.den <= 0 ||
        (video->codecpar->codec_id != AV_CODEC_ID_H264 && video->codecpar->codec_id != AV_CODEC_ID_HEVC)) return nil;
    NSMutableArray *audio = [NSMutableArray array], *text = [NSMutableArray array];
    _audio = -1;
    int opus = -1;
    NSUInteger audioNumber = 0;
    for (unsigned i = 0; i < _source->nb_streams; i++) {
        AVStream *stream = _source->streams[i];
        AVCodecParameters *parameters = stream->codecpar;
        enum AVCodecID codec = parameters->codec_id;
        if (parameters->codec_type == AVMEDIA_TYPE_AUDIO) audioNumber++;
        BOOL preferred = (stream->disposition & AV_DISPOSITION_DEFAULT) != 0;
        BOOL copyAudio = codec == AV_CODEC_ID_AAC || codec == AV_CODEC_ID_AC3 || codec == AV_CODEC_ID_EAC3;
        int channels = parameters->ch_layout.nb_channels;
        BOOL opusAudio = codec == AV_CODEC_ID_OPUS && (channels == 1 || channels == 2 || channels == 6);
        if (opusAudio && (opus < 0 || (preferred && !(_source->streams[opus]->disposition & AV_DISPOSITION_DEFAULT))))
            opus = i;
        if (copyAudio && (_audio < 0 || (preferred && !(_source->streams[_audio]->disposition & AV_DISPOSITION_DEFAULT))))
            _audio = i;
        if (!copyAudio && !opusAudio && codec != AV_CODEC_ID_SUBRIP && codec != AV_CODEC_ID_WEBVTT) continue;
        const AVDictionaryEntry *language = av_dict_get(stream->metadata, "language", NULL, 0);
        const AVDictionaryEntry *title = av_dict_get(stream->metadata, "title", NULL, 0);
        NSString *lang = language ? ([NSString stringWithUTF8String:language->value] ?: @"und") : @"und";
        NSString *name = title ? ([NSString stringWithUTF8String:title->value] ?: @"") : @"";
        NSMutableDictionary *track = [LGMKVCodecInfo(parameters) mutableCopy];
        [track addEntriesFromDictionary:@{@"id": @(i), @"language": lang, @"name": name,
            @"number": @(parameters->codec_type == AVMEDIA_TYPE_AUDIO ? audioNumber : text.count + 1),
            @"languageName": [lang isEqualToString:@"und"] ? @"" : ([NSLocale.currentLocale localizedStringForLanguageCode:lang] ?: lang),
            @"sampleRate": @(parameters->sample_rate),
            @"channels": @(channels), @"forced": @((stream->disposition & AV_DISPOSITION_FORCED) != 0),
            @"hearingImpaired": @((stream->disposition & AV_DISPOSITION_HEARING_IMPAIRED) != 0),
            @"visualImpaired": @((stream->disposition & AV_DISPOSITION_VISUAL_IMPAIRED) != 0),
            @"commentary": @((stream->disposition & AV_DISPOSITION_COMMENT) != 0)}];
        if (copyAudio || opusAudio) [audio addObject:track];
        else [text addObject:track];
    }
    if (_audio < 0) _audio = opus;
    if (_audio < 0) return nil;
    _duration = av_rescale_q(_source->duration, AV_TIME_BASE_Q, video->time_base);
    if (av_seek_frame(_source, _video, 0, AVSEEK_FLAG_BACKWARD) < 0) return nil;

    // Build a compact playlist from cues. Media packets are read only when a
    // client asks for the corresponding segment.
    int count = avformat_index_get_entries_count(video);
    if (count < 1 || count > 150000 || _duration <= 0) return nil;
    NSMutableArray<NSNumber *> *starts = [NSMutableArray array];
    int64_t target = av_rescale_q(6, (AVRational){1, 1}, video->time_base);
    int64_t maximum = av_rescale_q(30, (AVRational){1, 1}, video->time_base);
    for (int i = 0; i < count; i++) {
        const AVIndexEntry *entry = avformat_index_get_entry(video, i);
        int64_t time = entry->timestamp;
        if (!(entry->flags & AVINDEX_KEYFRAME) || time < 0 || time >= _duration) continue;
        if (!starts.count || time - starts.lastObject.longLongValue >= target) {
            if (time - starts.lastObject.longLongValue > maximum) return nil;
            [starts addObject:@(time)];
        }
    }
    if (!starts.count || starts.firstObject.longLongValue > av_rescale_q(1, (AVRational){1, 1}, video->time_base) ||
        _duration - starts.lastObject.longLongValue > maximum) return nil;
    _starts = [starts copy];
    NSMutableArray *boundaries = [NSMutableArray arrayWithObject:@0];
    for (NSUInteger i = 1; i < _starts.count; i++)
        [boundaries addObject:@(av_rescale_q(_starts[i].longLongValue, video->time_base, (AVRational){1, 1000}))];
    [boundaries addObject:@(av_rescale_q(_duration, video->time_base, (AVRational){1, 1000}))];
    NSMutableDictionary *videoInfo = [LGMKVCodecInfo(video->codecpar) mutableCopy];
    [videoInfo addEntriesFromDictionary:@{@"width": @(video->codecpar->width), @"height": @(video->codecpar->height)}];
    AVRational frameRate = video->avg_frame_rate;
    if (frameRate.num <= 0 || frameRate.den <= 0) frameRate = video->r_frame_rate;
    if (frameRate.num <= 0 || frameRate.den <= 0) return nil;
    videoInfo[@"frameRate"] = @(av_q2d(frameRate));
    if (video->codecpar->color_trc == AVCOL_TRC_SMPTE2084) videoInfo[@"range"] = @"PQ";
    else if (video->codecpar->color_trc == AVCOL_TRC_ARIB_STD_B67) videoInfo[@"range"] = @"HLG";
    _renditions = @{@"audio": audio, @"text": text, @"video": videoInfo,
        @"defaultAudio": @(_audio), @"boundaries": boundaries};
    NSMutableString *entries = [NSMutableString string];
    double longest = 0;
    for (NSUInteger i = 0; i < _starts.count; i++) {
        int64_t start = i ? _starts[i].longLongValue : 0;
        int64_t end = i + 1 == _starts.count ? _duration : _starts[i + 1].longLongValue;
        double seconds = (end - start) * av_q2d(video->time_base);
        longest = MAX(longest, seconds);
        [entries appendFormat:@"#EXTINF:%.6f,\nsegment-%lu.m4s\n", seconds, (unsigned long)i];
    }
    _playlist = [NSString stringWithFormat:@"#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-TARGETDURATION:%d\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXT-X-MAP:URI=\"init.mp4\"\n%@#EXT-X-ENDLIST\n",
        (int)ceil(longest), entries];
    return self;
}

// -2 preserves the original muxed output for the baseline validation probe.
// -1 is video-only. Nonnegative IDs identify an audio-only rendition.
- (NSData *)mux:(NSUInteger)index track:(int)trackID initialization:(NSData **)initialization {
    BOOL writeVideo = trackID < 0;
    BOOL writeAudio = trackID != -1;
    int audio = trackID >= 0 ? trackID : _audio;
    int audioOutput = writeVideo ? 1 : 0;
    AVFormatContext *output = NULL;
    AVIOContext *writer = NULL;
    AVPacket *packet = NULL, *tail = NULL;
    AVDictionary *options = NULL;
    NSMutableData *data = [NSMutableData data];
    LGMKVIO sink = {.deadline = NSProcessInfo.processInfo.systemUptime + 12, .output = (__bridge void *)data};
    uint8_t *buffer = NULL;
    AVStream *video = _source->streams[_video];
    BOOL success = NO, hasVideo = NO, hasAudio = NO;
    int64_t start = _starts[index].longLongValue;
    int64_t end = index + 1 == _starts.count ? _duration : _starts[index + 1].longLongValue;
    int status = 0;
    int inputTracks[] = {_video, audio};
    BOOL convertOpus = writeAudio && _source->streams[audio]->codecpar->codec_id == AV_CODEC_ID_OPUS;
    LGMKVOpus opus = {0};
    _reader.bytes = 0;
    _reader.deadline = sink.deadline;
    // Seek to the previous cue so audio interleaved before the target video
    // packet is available up to the exact segment boundary.
    int64_t preroll = start > 0 ? start - 1 : 0;
    if (av_seek_frame(_source, _video, preroll, AVSEEK_FLAG_BACKWARD) < 0) goto done;
    if (avformat_alloc_output_context2(&output, NULL, "mp4", NULL) < 0 || !output) goto done;
    buffer = av_malloc(65536);
    if (!buffer) goto done;
    writer = avio_alloc_context(buffer, 65536, 1, &sink, NULL, LGMKVWrite, NULL);
    if (!writer) { av_free(buffer); goto done; }
    output->pb = writer;
    output->flags |= AVFMT_FLAG_CUSTOM_IO;
    output->avoid_negative_ts = AVFMT_AVOID_NEG_TS_DISABLED;
    for (int i = writeVideo ? 0 : 1; i < (writeAudio ? 2 : 1); i++) {
        AVStream *in = _source->streams[inputTracks[i]];
        AVStream *out = avformat_new_stream(output, NULL);
        if (!out) goto done;
        if (i == 1 && convertOpus) {
            if (!LGOpusOpen(&opus, in->codecpar, out, av_rescale_q(start, video->time_base, LGOpusClock),
                            av_rescale_q(end, video->time_base, LGOpusClock))) goto done;
            continue;
        }
        if (avcodec_parameters_copy(out->codecpar, in->codecpar) < 0) goto done;
        out->time_base = in->time_base;
        out->avg_frame_rate = in->avg_frame_rate;
        out->codecpar->codec_tag = i == 0 ? (in->codecpar->codec_id == AV_CODEC_ID_HEVC
            ? MKTAG('h','v','c','1') : MKTAG('a','v','c','1')) : 0;
    }
    av_dict_set(&options, "movflags", "delay_moov+default_base_moof+frag_custom+frag_discont+skip_trailer+negative_cts_offsets", 0);
    av_dict_set(&options, "use_editlist", "0", 0);
    if (avformat_write_header(output, &options) < 0) goto done;
    avio_flush(writer);
    packet = av_packet_alloc();
    tail = av_packet_alloc();
    if (!packet || !tail) goto done;
    AVRational rate = video->avg_frame_rate;
    if (rate.num <= 0 || rate.den <= 0) rate = video->r_frame_rate;
    if (rate.num <= 0 || rate.den <= 0) goto done;
    AVRational frame = av_inv_q(rate);
    int64_t frameCount = 0, compositionDelay = av_rescale_q(4, frame, video->time_base);
    int64_t timelineOffset = av_rescale_q(100, (AVRational){1, 1000}, video->time_base);
    BOOL seenNextFragment = NO;
    int nextSync = -1;
    while ((status = av_read_frame(_source, packet)) >= 0) {
        int track = packet->stream_index == _video ? 0 : writeAudio && packet->stream_index == audio ? 1 : -1;
        if (track < 0) { av_packet_unref(packet); continue; }
        if (av_packet_get_side_data(packet, AV_PKT_DATA_NEW_EXTRADATA, NULL)) goto done;
        if (packet->pts == AV_NOPTS_VALUE) goto done;
        AVStream *in = _source->streams[packet->stream_index];
        int64_t pts = av_rescale_q(packet->pts, in->time_base, video->time_base);
        if (track == 0 && (packet->flags & AV_PKT_FLAG_KEY) && pts >= end && index + 1 < _starts.count) {
            if (!seenNextFragment && pts == end) nextSync = LGMKVVideoSync(packet, in->codecpar);
            seenNextFragment = YES;
        }
        if (track == 0 && !writeVideo) {
            av_packet_unref(packet);
            continue;
        }
        if (seenNextFragment && !writeAudio) break;
        if (track == 1 && convertOpus) {
            if (opus.cursor >= opus.end && seenNextFragment) break;
            if (opus.cursor < opus.end && !LGOpusPacket(&opus, output, packet, in->time_base, &hasAudio)) goto done;
            av_packet_unref(packet);
            continue;
        }
        if (track == 1 && pts >= end && seenNextFragment) break;
        if ((pts < start && (index || track == 0)) ||
            (pts >= end && (track == 0 || index + 1 < _starts.count)) || (track == 0 && seenNextFragment)) {
            av_packet_unref(packet);
            continue;
        }
        if (track == 0) {
            if (!hasVideo && (pts != start || !(packet->flags & AV_PKT_FLAG_KEY) ||
                LGMKVVideoSync(packet, in->codecpar) < 0)) goto done;
            hasVideo = YES;
            // Cue-based reads can leave initial DTS unset. Carry decode order
            // across fragments using the declared constant frame cadence.
            packet->dts = start + timelineOffset + av_rescale_q(frameCount, frame, video->time_base);
            packet->pts += timelineOffset + compositionDelay;
            packet->duration = start + timelineOffset + av_rescale_q(++frameCount, frame, video->time_base) - packet->dts;
            if (packet->duration <= 0 || packet->pts < packet->dts ||
                packet->pts - packet->dts > compositionDelay * 3) goto done;
        } else {
            hasAudio = YES;
        }
        if (packet->dts == AV_NOPTS_VALUE) packet->dts = packet->pts;
        if (track == 1) {
            // Keep priming packets and the same timeline offset in every fragment.
            int64_t offset = av_rescale_q(100, (AVRational){1, 1000}, in->time_base);
            packet->pts += offset;
            packet->dts += offset;
            if (packet->dts < 0) goto done;
        }
        packet->stream_index = track == 0 ? 0 : audioOutput;
        av_packet_rescale_ts(packet, in->time_base, output->streams[packet->stream_index]->time_base);
        if (track == 0) {
            if (tail->buf && av_interleaved_write_frame(output, tail) < 0) goto done;
            av_packet_move_ref(tail, packet);
        } else if (av_interleaved_write_frame(output, packet) < 0) goto done;
    }
    if ((status < 0 && status != AVERROR_EOF) || (writeVideo && !hasVideo)) goto done;
    if (writeVideo && index + 1 < _starts.count) {
        int64_t gap = (end - start) - av_rescale_q(frameCount, frame, video->time_base);
        // An open HEVC GOP may put leading pictures for this interval after
        // the next CRA in decode order. They require both sides of the
        // boundary. Hold the last sample through that short gap so each
        // fragment can start at its cue and keep continuous decode time.
        BOOL openGOP = video->codecpar->codec_id == AV_CODEC_ID_HEVC && nextSync == 21;
        if (gap < -2 || (gap > 2 && (!openGOP || gap > compositionDelay))) goto done;
        AVRational outputClock = output->streams[0]->time_base;
        tail->duration = av_rescale_q(end + timelineOffset, video->time_base, outputClock) - tail->dts;
        if (tail->duration <= 0) goto done;
    }
    if (writeVideo && av_interleaved_write_frame(output, tail) < 0) goto done;
    if (convertOpus) {
        if (opus.end - opus.cursor > 4800 ||
            !LGOpusFill(&opus, output, NULL, opus.end, &hasAudio) ||
            !LGOpusEncode(&opus, output, NULL, &hasAudio)) goto done;
    }
    if ((!writeVideo || hasVideo) && (!writeAudio || hasAudio) && av_interleaved_write_frame(output, NULL) >= 0 &&
        av_write_frame(output, NULL) >= 0 && av_write_trailer(output) >= 0) {
        avio_flush(writer);
        success = writer->error >= 0 && data.length > 0;
    }
done:
    LGOpusClose(&opus);
    av_packet_free(&tail);
    av_packet_free(&packet);
    av_dict_free(&options);
    avformat_free_context(output);
    LGMKVFreeIO(&writer);
    if (!success) return nil;
    const uint8_t *bytes = data.bytes;
    for (NSUInteger offset = 0; offset + 8 <= data.length;) {
        uint32_t size = AV_RB32(bytes + offset);
        if (size < 8 || size > data.length - offset) break;
        if (!memcmp(bytes + offset + 4, "moof", 4)) {
            if (initialization) *initialization = [data subdataWithRange:NSMakeRange(0, offset)];
            return [data subdataWithRange:NSMakeRange(offset, data.length - offset)];
        }
        offset += size;
    }
    return nil;
}

- (NSData *)initialization {
    if (!_initialization) {
        NSData *header = nil;
        _firstFragment = [self mux:0 track:-2 initialization:&header];
        _initialization = header;
    }
    return _initialization;
}
- (NSString *)playlist { return _playlist; }
- (NSData *)segment:(NSUInteger)index {
    if (index == 0 && _firstFragment) {
        NSData *first = _firstFragment;
        _firstFragment = nil;
        return first;
    }
    return index < _starts.count ? [self mux:index track:-2 initialization:NULL] : nil;
}

- (NSString *)renditionsJSON {
    NSData *json = [NSJSONSerialization dataWithJSONObject:_renditions options:0 error:nil];
    return [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
}

- (BOOL)includesTrack:(int)track inGroup:(NSString *)group {
    for (NSDictionary *row in _renditions[group])
        if ([row[@"id"] intValue] == track) return YES;
    return NO;
}

- (NSData *)initializationForTrack:(int)track {
    if (track != -1 && ![self includesTrack:track inGroup:@"audio"]) return nil;
    NSData *header = nil;
    [self mux:0 track:track initialization:&header];
    return header;
}

- (NSData *)fragment:(NSUInteger)index track:(int)track {
    if (index >= _starts.count || (track != -1 && ![self includesTrack:track inGroup:@"audio"])) return nil;
    return [self mux:index track:track initialization:NULL];
}

// Matroska stores UTF-8 text in each SubRip/WebVTT block. Read around
// the requested segment, including preceding cues that still overlap it.
- (NSString *)textSegment:(NSUInteger)index track:(int)track {
    if (index >= _starts.count || ![self includesTrack:track inGroup:@"text"]) return nil;
    AVRational clock = (AVRational){1, 1000};
    AVRational timeBase = _source->streams[_video]->time_base;
    NSArray *boundaries = _renditions[@"boundaries"];
    int64_t start = [boundaries[index] longLongValue], end = [boundaries[index + 1] longLongValue];
    _reader.bytes = 0;
    _reader.deadline = NSProcessInfo.processInfo.systemUptime + 12;
    // The same bound applies to accepted embedded cue lengths.
    int64_t preroll = av_rescale_q(MAX(0, start - 30000), clock, timeBase);
    if (av_seek_frame(_source, _video, preroll, AVSEEK_FLAG_BACKWARD) < 0) return nil;
    AVPacket *packet = av_packet_alloc();
    if (!packet) return nil;
    NSMutableArray *cues = [NSMutableArray array];
    AVStream *stream = _source->streams[track];
    int status;
    while ((status = av_read_frame(_source, packet)) >= 0) {
        if (packet->pts != AV_NOPTS_VALUE && packet->stream_index == _video &&
            (packet->flags & AV_PKT_FLAG_KEY) && av_rescale_q(packet->pts, timeBase, clock) >= end) break;
        if (packet->stream_index == track && packet->pts != AV_NOPTS_VALUE &&
            packet->duration > 0 && packet->size > 0 && packet->size <= 16384) {
            int64_t first = av_rescale_q(packet->pts, stream->time_base, clock);
            int64_t length = av_rescale_q(packet->duration, stream->time_base, clock);
            if (first < end && length > 0 && length <= 30000 && first + length > start) {
                NSString *text = [[NSString alloc] initWithBytes:packet->data length:packet->size encoding:NSUTF8StringEncoding];
                if (text.length) [cues addObject:@[@(first), @(first + length), text]];
            }
        }
        av_packet_unref(packet);
        if (cues.count > 2048) { status = AVERROR_INVALIDDATA; break; }
    }
    av_packet_free(&packet);
    if (status < 0 && status != AVERROR_EOF) return nil;
    NSData *json = [NSJSONSerialization dataWithJSONObject:cues options:0 error:nil];
    return [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
}

- (void)dealloc {
    avformat_close_input(&_source);
    LGMKVFreeIO(&_input);
    if (_file >= 0) close(_file);
}
@end

#endif
