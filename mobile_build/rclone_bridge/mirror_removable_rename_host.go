//go:build !android

// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package main

func sdRenameVacant(from, to string) error { return sdCheckedRename(from, to) }
