// TEST_STAGE = TestStage.REGRESSION
package main

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/base64"
	"errors"
	"io"
	"math/rand"
	"os"
	"sync"
	"testing"

	"github.com/rclone/rclone/fs/config/obscure"
)

type archiveCountingReader struct {
	io.ReaderAt
	calls int
}

func (reader *archiveCountingReader) ReadAt(data []byte, offset int64) (int, error) {
	reader.calls++
	return reader.ReaderAt.ReadAt(data, offset)
}

func TestArchiveBlocksRangesAndReuse(t *testing.T) {
	data := make([]byte, archiveBlockSize*2+17)
	rand.New(rand.NewSource(17)).Read(data)
	source := &archiveCountingReader{ReaderAt: bytes.NewReader(data)}
	reader := &archiveBlockReader{ctx: context.Background(), source: source, size: int64(len(data))}
	defer reader.close()
	for _, offset := range []int64{0, 7, 1024} {
		got := make([]byte, 31)
		if n, err := reader.ReadAt(got, offset); err != nil || n != len(got) || !bytes.Equal(got, data[offset:offset+31]) {
			t.Fatalf("range %d: %d %v", offset, n, err)
		}
	}
	if source.calls != 1 {
		t.Fatalf("same block decrypted %d times", source.calls)
	}
	got := make([]byte, len(data)-archiveBlockSize+5)
	if n, err := reader.ReadAt(got, archiveBlockSize-5); err != nil || n != len(got) || !bytes.Equal(got, data[archiveBlockSize-5:]) {
		t.Fatalf("cross-block range: %d %v", n, err)
	}
	if source.calls != 3 {
		t.Fatalf("three blocks required %d decryptions", source.calls)
	}
	if n, err := reader.ReadAt(make([]byte, 18), int64(len(data)-17)); n != 17 || err != io.EOF {
		t.Fatalf("partial EOF: %d %v", n, err)
	}
	if n, err := reader.ReadAt(nil, int64(len(data))); n != 0 || err != nil {
		t.Fatalf("empty range: %d %v", n, err)
	}
	if _, err := reader.ReadAt(make([]byte, 1), -1); err == nil {
		t.Fatal("negative range accepted")
	}
	retained := reader.data
	reader.close()
	if !bytes.Equal(retained, make([]byte, len(retained))) {
		t.Fatal("request cache not cleared")
	}
}

func TestArchiveBlocksCancellationAndConcurrentReads(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	data := bytes.Repeat([]byte{42}, archiveBlockSize*2+3)
	reader := &archiveBlockReader{ctx: ctx, source: bytes.NewReader(data), size: int64(len(data))}
	defer reader.close()
	var workers sync.WaitGroup
	for i := 0; i < 8; i++ {
		workers.Add(1)
		go func(offset int64) {
			defer workers.Done()
			got := make([]byte, 100)
			if _, err := reader.ReadAt(got, offset); err != nil || !bytes.Equal(got, data[offset:offset+100]) {
				t.Errorf("concurrent range: %v", err)
			}
		}(int64(i * 10000))
	}
	workers.Wait()
	cancel()
	if _, err := reader.ReadAt(make([]byte, 1), 70000); !errors.Is(err, context.Canceled) {
		t.Fatalf("cached bytes bypass cancellation: %v", err)
	}
}

func comicArchiveFixture(t testing.TB) ([]byte, []byte, *cryptReaderAt) {
	t.Helper()
	page := make([]byte, 3*1024*1024)
	rand.New(rand.NewSource(17)).Read(page)
	var plain bytes.Buffer
	archive := zip.NewWriter(&plain)
	member, err := archive.Create("synthetic-page.jpg")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = member.Write(page); err != nil {
		t.Fatal(err)
	}
	if err = archive.Close(); err != nil {
		t.Fatal(err)
	}
	cipher, err := cryptCipher(map[string]string{"password": obscure.MustObscure("synthetic-only")})
	if err != nil {
		t.Fatal(err)
	}
	stream, err := cipher.EncryptData(bytes.NewReader(plain.Bytes()))
	if err != nil {
		t.Fatal(err)
	}
	encrypted, err := io.ReadAll(stream)
	if err != nil {
		t.Fatal(err)
	}
	file, err := os.CreateTemp(t.TempDir(), "ciphertext")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { file.Close() })
	if _, err = file.Write(encrypted); err != nil {
		t.Fatal(err)
	}
	return page, plain.Bytes(), &cryptReaderAt{context.Background(), file, cipher, int64(plain.Len())}
}

func TestArchiveBlocksEncryptedMemberAndAuthentication(t *testing.T) {
	page, plain, source := comicArchiveFixture(t)
	counted := &archiveCountingReader{ReaderAt: source}
	reader := &archiveBlockReader{ctx: context.Background(), source: counted, size: int64(len(plain))}
	result, err := archiveContents(context.Background(), reader, reader.size, "", "synthetic-page.jpg", 10000, 16*1024*1024)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := base64.StdEncoding.DecodeString(result.(map[string]string)["data"])
	if err != nil || !bytes.Equal(decoded, page) {
		t.Fatal("page content changed")
	}
	if counted.calls > len(plain)/archiveBlockSize+5 {
		t.Fatalf("small ZIP reads repeated block decryption: %d", counted.calls)
	}
	reader.close()
	// Corrupt ciphertext in the first data block. A new request must authenticate
	// it again instead of seeing bytes retained by the previous request.
	corrupt := make([]byte, 1)
	if _, err = source.file.ReadAt(corrupt, 64); err != nil {
		t.Fatal(err)
	}
	corrupt[0] ^= 1
	if _, err = source.file.WriteAt(corrupt, 64); err != nil {
		t.Fatal(err)
	}
	fresh := &archiveBlockReader{ctx: context.Background(), source: source, size: source.size}
	defer fresh.close()
	if _, err = fresh.ReadAt(make([]byte, 1), 0); err == nil || len(fresh.data) != 0 {
		t.Fatal("corrupted block was cached or accepted")
	}
}

func BenchmarkCryptArchivePage(b *testing.B) {
	_, plain, source := comicArchiveFixture(b)
	for _, reuse := range []bool{false, true} {
		name := "baseline"
		if reuse {
			name = "block-reuse"
		}
		b.Run(name, func(b *testing.B) {
			b.ReportAllocs()
			b.SetBytes(3 * 1024 * 1024)
			for i := 0; i < b.N; i++ {
				var input io.ReaderAt = source
				blocks := &archiveBlockReader{ctx: context.Background(), source: source, size: int64(len(plain))}
				if reuse {
					input = blocks
				}
				_, err := archiveContents(context.Background(), input, int64(len(plain)), "", "synthetic-page.jpg", 10000, 16*1024*1024)
				blocks.close()
				if err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
