package main

import (
	"context"
	"errors"
	"io"
	"os"

	"golang.org/x/sys/unix"
)

// Duplicate only an empty regular file. The caller owns publication and cleanup.
func privateOutput(fd int) (*os.File, error) {
	if fd < 3 {
		return nil, errors.New("invalid private output descriptor")
	}
	copied, err := unix.Dup(fd)
	if err != nil {
		return nil, errors.New("private output unavailable")
	}
	file := os.NewFile(uintptr(copied), "private-output")
	info, err := file.Stat()
	offset, seekErr := file.Seek(0, io.SeekCurrent)
	var stat unix.Stat_t
	statErr := unix.Fstat(copied, &stat)
	if err != nil || seekErr != nil || statErr != nil || stat.Nlink != 1 || !info.Mode().IsRegular() || info.Size() != 0 || offset != 0 {
		file.Close()
		return nil, errors.New("private output must be a new independent regular file")
	}
	return file, nil
}

func readBounded(ctx context.Context, reader io.Reader, limit int) ([]byte, error) {
	data := []byte{}
	buffer := make([]byte, 64*1024)
	for {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		n, err := reader.Read(buffer)
		if len(data)+n > limit {
			return nil, errors.New("content exceeds memory limit")
		}
		data = append(data, buffer[:n]...)
		if err == io.EOF {
			return data, nil
		}
		if err != nil {
			return nil, err
		}
	}
}
