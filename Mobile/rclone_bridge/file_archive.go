package main

import (
	"context"
	"errors"
	"golang.org/x/sys/unix"
	"os"
)

// Read ordinary ZIP/CBZ members, including AES and ZipCrypto, without credentials
// or extraction. The caller keeps the unchanged encrypted archive on disk.
func fileArchive(ctx context.Context, fd int, password, member string) (any, error) {
	if fd < 3 {
		return nil, errors.New("invalid archive descriptor")
	}
	duplicate, err := unix.Dup(fd)
	if err != nil {
		return nil, err
	}
	file := os.NewFile(uintptr(duplicate), "local-archive")
	defer file.Close()
	info, err := file.Stat()
	var stat unix.Stat_t
	if err != nil || !info.Mode().IsRegular() || unix.Fstat(duplicate, &stat) != nil || stat.Nlink != 1 {
		return nil, errors.New("archive must be independent and regular")
	}
	return archiveContents(ctx, file, info.Size(), password, member, 5000, 8*1024*1024)
}
