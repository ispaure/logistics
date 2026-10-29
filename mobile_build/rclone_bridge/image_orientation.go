package main

import (
	"bytes"
	"encoding/binary"
)

// imageOrientation reads only bounded primary EXIF metadata; malformed optional
// metadata falls back to encoded orientation. Image decoding validates pixels.
func imageOrientation(data []byte) int {
	tiff := func(data []byte) int {
		data = bytes.TrimPrefix(data, []byte("Exif\x00\x00"))
		if len(data) < 8 {
			return 1
		}
		var order binary.ByteOrder
		if string(data[:2]) == "II" {
			order = binary.LittleEndian
		} else if string(data[:2]) == "MM" {
			order = binary.BigEndian
		} else {
			return 1
		}
		if order.Uint16(data[2:4]) != 42 {
			return 1
		}
		offset := uint64(order.Uint32(data[4:8]))
		if offset+2 > uint64(len(data)) {
			return 1
		}
		count := min(int(order.Uint16(data[offset:offset+2])), 4096)
		for i := 0; i < count; i++ {
			entry := offset + 2 + uint64(i)*12
			if entry+12 > uint64(len(data)) {
				return 1
			}
			if order.Uint16(data[entry:entry+2]) == 274 && order.Uint16(data[entry+2:entry+4]) == 3 && order.Uint32(data[entry+4:entry+8]) == 1 {
				value := int(order.Uint16(data[entry+8 : entry+10]))
				if value >= 1 && value <= 8 {
					return value
				}
				return 1
			}
		}
		return 1
	}
	if bytes.HasPrefix(data, []byte{255, 216}) {
		for offset := 2; offset+4 <= len(data) && data[offset] == 255; {
			for offset < len(data) && data[offset] == 255 {
				offset++
			}
			if offset >= len(data) {
				break
			}
			marker := data[offset]
			offset++
			if marker == 0xDA || marker == 0xD9 {
				break
			}
			if marker == 1 || marker >= 0xD0 && marker <= 0xD8 {
				continue
			}
			if offset+2 > len(data) {
				break
			}
			size := int(binary.BigEndian.Uint16(data[offset : offset+2]))
			if size < 2 || size > len(data)-offset {
				break
			}
			if marker == 0xE1 && bytes.HasPrefix(data[offset+2:offset+size], []byte("Exif\x00\x00")) {
				return tiff(data[offset+2 : offset+size])
			}
			offset += size
		}
	} else if len(data) >= 12 && string(data[:4]) == "RIFF" && string(data[8:12]) == "WEBP" {
		for offset := uint64(12); offset+8 <= uint64(len(data)); {
			size := uint64(binary.LittleEndian.Uint32(data[offset+4 : offset+8]))
			if offset+8+size > uint64(len(data)) {
				break
			}
			if string(data[offset:offset+4]) == "EXIF" {
				return tiff(data[offset+8 : offset+8+size])
			}
			offset += 8 + size + size%2
		}
	} else if bytes.HasPrefix(data, []byte("\x89PNG\r\n\x1a\n")) {
		for offset := uint64(8); offset+12 <= uint64(len(data)); {
			size := uint64(binary.BigEndian.Uint32(data[offset : offset+4]))
			if offset+12+size > uint64(len(data)) {
				break
			}
			if string(data[offset+4:offset+8]) == "eXIf" {
				return tiff(data[offset+8 : offset+8+size])
			}
			offset += 12 + size
		}
	}
	return 1
}

// Map an oriented display coordinate back to encoded pixels without allocating
// a full rotated image. Covers mirrored orientations as well as quarter turns.
func encodedPoint(x, y, width, height, orientation int) (int, int) {
	switch orientation {
	case 2:
		return width - 1 - x, y
	case 3:
		return width - 1 - x, height - 1 - y
	case 4:
		return x, height - 1 - y
	case 5:
		return y, x
	case 6:
		return y, height - 1 - x
	case 7:
		return width - 1 - y, height - 1 - x
	case 8:
		return width - 1 - y, x
	default:
		return x, y
	}
}
