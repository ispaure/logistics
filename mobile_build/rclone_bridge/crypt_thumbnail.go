package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"errors"
	"image"
	_ "image/jpeg"
	"image/png"
	"io"
	"os"

	_ "golang.org/x/image/webp"
	"golang.org/x/sys/unix"
)

func nativeThumbnail(ctx context.Context, data []byte, width, height int) (map[string]string, error) {
	if width < 1 || height < 1 || width > 512 || height > 512 {
		return nil, errors.New("invalid thumbnail dimensions")
	}
	config, _, err := image.DecodeConfig(bytes.NewReader(data))
	if err != nil || config.Width < 1 || config.Height < 1 || int64(config.Width)*int64(config.Height) > 16*1024*1024 {
		return nil, errors.New("image exceeds decode dimensions")
	}
	original, _, err := image.Decode(bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	if width*config.Height > height*config.Width {
		width = max(1, height*config.Width/config.Height)
	} else {
		height = max(1, width*config.Height/config.Width)
	}
	small := image.NewNRGBA(image.Rect(0, 0, width, height))
	bounds := original.Bounds()
	for y := 0; y < height; y++ {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		for x := 0; x < width; x++ {
			small.Set(x, y, original.At(bounds.Min.X+x*config.Width/width, bounds.Min.Y+y*config.Height/height))
		}
	}
	var output bytes.Buffer
	if err = png.Encode(&output, small); err != nil {
		return nil, err
	}
	return map[string]string{"data": base64.StdEncoding.EncodeToString(output.Bytes())}, nil
}

func cryptThumbnail(ctx context.Context, name, encrypted, identity, password, member string, fd, width, height int) (map[string]string, error) {
	var data []byte
	if member != "" {
		result, err := cryptArchive(ctx, name, encrypted, identity, password, member, fd)
		if err != nil {
			return nil, err
		}
		data, err = base64.StdEncoding.DecodeString(result.(map[string]string)["data"])
		if err != nil {
			return nil, err
		}
	} else {
		_, reader, err := openCryptReader(ctx, name, encrypted, identity, fd)
		if err != nil {
			return nil, err
		}
		defer reader.file.Close()
		if reader.size > 16*1024*1024 {
			return nil, errors.New("image exceeds preview buffer")
		}
		stream, err := reader.stream(0, -1)
		if err != nil {
			return nil, err
		}
		defer stream.Close()
		data, err = readBounded(ctx, stream, 16*1024*1024)
		if err != nil {
			return nil, err
		}
	}
	return nativeThumbnail(ctx, data, width, height)
}

func fileThumbnail(ctx context.Context, fd, width, height int) (map[string]string, error) {
	if fd < 3 {
		return nil, errors.New("invalid image descriptor")
	}
	copied, err := unix.Dup(fd)
	if err != nil {
		return nil, err
	}
	file := os.NewFile(uintptr(copied), "image-preview")
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() > 16*1024*1024 {
		return nil, errors.New("invalid preview file")
	}
	data, err := readBounded(ctx, io.NewSectionReader(file, 0, info.Size()), 16*1024*1024)
	if err != nil {
		return nil, err
	}
	return nativeThumbnail(ctx, data, width, height)
}
