// TEST_STAGE = TestStage.SMOKE
package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/binary"
	"image"
	"image/color"
	"image/jpeg"
	"image/png"
	"testing"
)

func TestThumbnailEXIFOrientation(t *testing.T) {
	source := image.NewRGBA(image.Rect(0, 0, 30, 50))
	for y := 0; y < 50; y++ {
		for x := 0; x < 30; x++ {
			source.Set(x, y, color.RGBA{uint8(x * 8), uint8(y * 5), 0, 255})
		}
	}
	var encoded bytes.Buffer
	if err := jpeg.Encode(&encoded, source, &jpeg.Options{Quality: 100}); err != nil {
		t.Fatal(err)
	}
	raw := encoded.Bytes()
	for orientation := 1; orientation <= 8; orientation++ {
		exif := []byte{'E', 'x', 'i', 'f', 0, 0, 'I', 'I', 42, 0, 8, 0, 0, 0, 1, 0, 0x12, 1, 3, 0, 1, 0, 0, 0, byte(orientation), 0, 0, 0, 0, 0, 0, 0}
		segment := []byte{255, 0xE1, 0, 0}
		binary.BigEndian.PutUint16(segment[2:], uint16(len(exif)+2))
		data := append(append(append(append([]byte{}, raw[:2]...), segment...), exif...), raw[2:]...)
		if imageOrientation(data) != orientation {
			t.Fatalf("metadata %d", orientation)
		}
		result, err := nativeThumbnail(context.Background(), data, 100, 100)
		if err != nil {
			t.Fatal(err)
		}
		pixels, err := base64.StdEncoding.DecodeString(result["data"])
		if err != nil {
			t.Fatal(err)
		}
		thumbnail, err := png.Decode(bytes.NewReader(pixels))
		if err != nil {
			t.Fatal(err)
		}
		width, height := 60, 100
		if orientation >= 5 {
			width, height = 100, 60
		}
		if thumbnail.Bounds().Dx() != width || thumbnail.Bounds().Dy() != height {
			t.Fatalf("orientation %d: %v", orientation, thumbnail.Bounds())
		}
		original, _, _ := image.Decode(bytes.NewReader(data))
		sx, sy := encodedPoint(0, 0, 30, 50, orientation)
		expected := color.NRGBAModel.Convert(original.At(sx, sy))
		actual := color.NRGBAModel.Convert(thumbnail.At(0, 0))
		if expected != actual {
			t.Fatalf("orientation %d: got %v expected %v", orientation, actual, expected)
		}
	}
}

func TestMalformedOrientation(t *testing.T) {
	for _, data := range [][]byte{nil, []byte("RIFF1234WEBPEXIF\xff\xff\xff\xff"), {255, 216, 255, 225, 255, 255}} {
		if imageOrientation(data) != 1 {
			t.Fatal("malformed metadata changed pixels")
		}
	}
}
