// TEST_STAGE = TestStage.REGRESSION
package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"image/png"
	"testing"
)

func TestWebPThumbnail(t *testing.T) {
	for _, encoded := range []string{
		"UklGRhwAAABXRUJQVlA4TA8AAAAvAYAAEAcQ/Y8CBiKi/wEA",
		"UklGRjwAAABXRUJQVlA4IDAAAADQAQCdASoCAAMAAUAmJaACdLoB+AADsAD+8ut//NgVzXPv9//S4P0uD9Lg/9KQAAA=",
		"UklGRl4AAABXRUJQVlA4WAoAAAAQAAAAAQAAAgAAQUxQSAcAAAAAgICAgICAAFZQOCAwAAAA0AEAnQEqAgADAAFAJiWgAnS6AfgAA7AA/vLrf/zYFc1z7/f/0uD9Lg/S4P/SkAAA",
	} {
		data, err := base64.StdEncoding.DecodeString(encoded)
		if err != nil {
			t.Fatal(err)
		}
		result, err := nativeThumbnail(context.Background(), data, 20, 30)
		if err != nil {
			t.Fatal(err)
		}
		output, err := base64.StdEncoding.DecodeString(result["data"])
		if err != nil {
			t.Fatal(err)
		}
		image, err := png.Decode(bytes.NewReader(output))
		if err != nil {
			t.Fatal(err)
		}
		if image.Bounds().Dx() != 20 || image.Bounds().Dy() != 30 {
			t.Fatal(image.Bounds())
		}
		if _, err = nativeThumbnail(context.Background(), data[:16], 20, 30); err == nil {
			t.Fatal("truncated WebP accepted")
		}
	}
}
