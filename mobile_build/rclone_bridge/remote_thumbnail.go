package main

import (
	"context"
	"errors"
	"github.com/rclone/rclone/backend/crypt"
	"github.com/rclone/rclone/fs"
	"github.com/yeka/zip"
	"io"
	"path"
	"sort"
	"strings"
)

type remoteReaderAt struct {
	ctx    context.Context
	object fs.Object
	cipher *crypt.Cipher
}

func (reader remoteReaderAt) open(ctx context.Context, offset, limit int64) (io.ReadCloser, error) {
	end := int64(-1)
	if limit >= 0 {
		end = offset + limit - 1
	}
	return reader.object.Open(ctx, &fs.RangeOption{Start: offset, End: end})
}
func (reader remoteReaderAt) ReadAt(buffer []byte, offset int64) (int, error) {
	var stream io.ReadCloser
	var err error
	if reader.cipher != nil {
		stream, err = reader.cipher.DecryptDataSeek(reader.ctx, reader.open, offset, int64(len(buffer)))
	} else {
		stream, err = reader.open(reader.ctx, offset, int64(len(buffer)))
	}
	if err != nil {
		return 0, err
	}
	defer stream.Close()
	return io.ReadFull(stream, buffer)
}

func remoteThumbnail(ctx context.Context, name, p, password string, width, height int) (map[string]string, error) {
	if !validPath(p) || p == "" {
		return nil, errors.New("invalid preview path")
	}
	var cipher *crypt.Cipher
	backing, objectPath := name, p
	if kind, _ := store.GetValue(name, "type"); kind == "crypt" {
		var root string
		var err error
		cipher, backing, root, _, err = cryptConnection(name)
		if err != nil {
			return nil, err
		}
		objectPath = path.Join(root, cipher.EncryptFileName(p))
	}
	backend, err := remote(ctx, backing)
	if err != nil {
		return nil, err
	}
	object, err := backend.NewObject(ctx, objectPath)
	if err != nil {
		return nil, err
	}
	size := object.Size()
	if cipher != nil {
		size, err = cipher.DecryptedSize(size)
		if err != nil {
			return nil, err
		}
	}
	source := remoteReaderAt{ctx, object, cipher}
	suffix := strings.ToLower(path.Ext(p))
	var data []byte
	if suffix == ".zip" || suffix == ".cbz" || suffix == ".epub" {
		archive, err := zip.NewReader(source, size)
		if err != nil || len(archive.File) > 10000 {
			return nil, errors.New("invalid preview archive")
		}
		images := []*zip.File{}
		for _, file := range archive.File {
			extension := strings.ToLower(path.Ext(file.Name))
			if validPath(file.Name) && !file.FileInfo().IsDir() && (extension == ".png" || extension == ".jpg" || extension == ".jpeg" || extension == ".webp") && file.UncompressedSize64 <= 16*1024*1024 {
				images = append(images, file)
			}
		}
		sort.Slice(images, func(i, j int) bool {
			a, b := strings.ToLower(images[i].Name), strings.ToLower(images[j].Name)
			if strings.Contains(a, "cover") != strings.Contains(b, "cover") {
				return strings.Contains(a, "cover")
			}
			return a < b
		})
		if len(images) == 0 {
			return nil, errors.New("no preview image")
		}
		file := images[0]
		if file.IsEncrypted() {
			if password == "" {
				return nil, archivePasswordError
			}
			file.SetPassword(password)
		}
		stream, err := file.Open()
		if err != nil {
			return nil, archivePasswordError
		}
		data, err = readBounded(ctx, stream, 16*1024*1024)
		closeErr := stream.Close()
		if err != nil || closeErr != nil {
			return nil, archivePasswordError
		}
	} else {
		if size > 16*1024*1024 || size < 0 {
			return nil, errors.New("image exceeds preview buffer")
		}
		data = make([]byte, int(size))
		if _, err = source.ReadAt(data, 0); err != nil {
			return nil, err
		}
	}
	return nativeThumbnail(ctx, data, width, height)
}
