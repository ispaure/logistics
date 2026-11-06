// TEST_STAGE = TestStage.REGRESSION
package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/yeka/zip"
)

func TestStandaloneEncryptedArchiveWithoutCredentials(t *testing.T) {
	for _, method := range []zip.EncryptionMethod{zip.StandardEncryption, zip.AES256Encryption} {
		file, err := os.Create(filepath.Join(t.TempDir(), "comic.cbz"))
		if err != nil {
			t.Fatal(err)
		}
		writer := zip.NewWriter(file)
		page, err := writer.Encrypt("page.png", "fixture-password", method)
		if err != nil {
			t.Fatal(err)
		}
		if _, err = page.Write([]byte("fixture page")); err != nil {
			t.Fatal(err)
		}
		if err = writer.Close(); err != nil {
			t.Fatal(err)
		}
		if _, err = fileArchive(context.Background(), int(file.Fd()), "", ""); err != nil {
			t.Fatal(err)
		}
		for _, password := range []string{"", "wrong"} {
			if _, err = fileArchive(context.Background(), int(file.Fd()), password, "page.png"); !errors.Is(err, archivePasswordError) {
				t.Fatalf("wrong password was not rejected: %v", err)
			}
		}
		result, err := fileArchive(context.Background(), int(file.Fd()), "fixture-password", "page.png")
		if err != nil {
			t.Fatal(err)
		}
		data, err := base64.StdEncoding.DecodeString(result.(map[string]string)["data"])
		if err != nil || string(data) != "fixture page" {
			t.Fatal("bad decoded page")
		}
		file.Close()
	}
}

func TestStandaloneArchiveValidatesAllHeadersBeforeReading(t *testing.T) {
	file, err := os.Create(filepath.Join(t.TempDir(), "unsafe.cbz"))
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer := zip.NewWriter(file)
	first, _ := writer.Create("page.png")
	first.Write([]byte("page"))
	unsafe, _ := writer.Create("../escape.png")
	unsafe.Write([]byte("outside"))
	if err = writer.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err = fileArchive(context.Background(), int(file.Fd()), "", "page.png"); err == nil {
		t.Fatal("unsafe later header accepted")
	}
}

type archivePayloadFault struct {
	io.ReaderAt
	offset int64
	fail   func() error
	hits   int
}

func (r *archivePayloadFault) ReadAt(p []byte, off int64) (int, error) {
	if off == r.offset {
		r.hits++
		return 0, r.fail()
	}
	return r.ReaderAt.ReadAt(p, off)
}

func TestPlainArchivePayloadFailure(t *testing.T) {
	var buf bytes.Buffer
	w := zip.NewWriter(&buf)
	f, err := w.CreateHeader(&zip.FileHeader{Name: "page.txt", Method: zip.Store})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = io.WriteString(f, "synthetic payload"); err != nil {
		t.Fatal(err)
	}
	if err = w.Close(); err != nil {
		t.Fatal(err)
	}
	src := bytes.NewReader(buf.Bytes())
	z, err := zip.NewReader(src, src.Size())
	if err != nil {
		t.Fatal(err)
	}
	offset, err := z.File[0].DataOffset()
	if err != nil {
		t.Fatal(err)
	}
	if _, err = archiveContents(context.Background(), src, src.Size(), "", "page.txt", 4, 1024); err != nil {
		t.Fatal(err)
	}
	sentinel := errors.New("synthetic private provider path")
	for _, tc := range []struct {
		name string
		want error
	}{{"io", sentinel}, {"cancel", context.Canceled}} {
		t.Run(tc.name, func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			r := &archivePayloadFault{ReaderAt: src, offset: offset, fail: func() error {
				if tc.want == context.Canceled {
					cancel()
				}
				return tc.want
			}}
			_, err := archiveContents(ctx, r, src.Size(), "", "page.txt", 4, 1024)
			reply := encodeReply("file_archive", nil, err)
			if r.hits != 1 || !errors.Is(err, tc.want) || errors.Is(err, archivePasswordError) || strings.Contains(reply, `"error_code":"archive_password"`) {
				t.Fatalf("payload error lost or misclassified: want %v, got %v", tc.want, err)
			}
			if tc.want == sentinel && (strings.Contains(reply, sentinel.Error()) || !strings.Contains(reply, "Could not read the inner ZIP member.")) {
				t.Fatalf("unsafe or missing error message: %s", reply)
			}
		})
	}
}

func TestEncryptedArchivePayloadCancellationWithCorrectPassword(t *testing.T) {
	for name, method := range map[string]zip.EncryptionMethod{"ZipCrypto": zip.StandardEncryption, "AES-256": zip.AES256Encryption} {
		t.Run(name, func(t *testing.T) {
			var buf bytes.Buffer
			w := zip.NewWriter(&buf)
			f, err := w.Encrypt("page.txt", "fixture-password", method)
			if err != nil {
				t.Fatal(err)
			}
			if _, err = io.WriteString(f, "fixture page"); err != nil {
				t.Fatal(err)
			}
			if err = w.Close(); err != nil {
				t.Fatal(err)
			}
			src := bytes.NewReader(buf.Bytes())
			archive, err := zip.NewReader(src, src.Size())
			if err != nil {
				t.Fatal(err)
			}
			offset, err := archive.File[0].DataOffset()
			if err != nil {
				t.Fatal(err)
			}
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			r := &archivePayloadFault{ReaderAt: src, offset: offset, fail: func() error {
				cancel()
				return errors.New("synthetic underlying I/O failure")
			}}
			_, err = archiveContents(ctx, r, src.Size(), "fixture-password", "page.txt", 4, 1024)
			if r.hits != 1 || !errors.Is(err, context.Canceled) || strings.Contains(encodeReply("file_archive", nil, err), `"error_code":"archive_password"`) {
				t.Fatalf("encrypted payload cancellation misclassified: reads=%d, error=%v", r.hits, err)
			}
		})
	}
}
