package main

import (
	"encoding/json"
	"io"
	"sync"
)

var mirrorProgressState struct {
	sync.Mutex
	Run, Phase  string
	Done, Total int64
}

func mirrorPhase(run, phase string, total int64) {
	mirrorProgressState.Lock()
	defer mirrorProgressState.Unlock()
	mirrorProgressState.Run, mirrorProgressState.Phase = run, phase
	mirrorProgressState.Done, mirrorProgressState.Total = 0, total
}

type mirrorCounter struct {
	reader io.Reader
	run    string
}

func (reader mirrorCounter) Read(data []byte) (int, error) {
	n, err := reader.reader.Read(data)
	mirrorProgressState.Lock()
	if mirrorProgressState.Run == reader.run {
		mirrorProgressState.Done += int64(n)
	}
	mirrorProgressState.Unlock()
	return n, err
}

func mirrorProgress(input string) string {
	var request struct {
		Run string `json:"run"`
	}
	if len(input) > 1024 || json.Unmarshal([]byte(input), &request) != nil {
		return `{"ok":false,"error":"invalid progress request"}`
	}
	mirrorProgressState.Lock()
	defer mirrorProgressState.Unlock()
	result := map[string]any{"phase": "", "done": 0, "total": 0}
	if request.Run != "" && request.Run == mirrorProgressState.Run {
		result = map[string]any{"phase": mirrorProgressState.Phase, "done": mirrorProgressState.Done, "total": mirrorProgressState.Total}
	}
	data, _ := json.Marshal(map[string]any{"ok": true, "result": result})
	return string(data)
}
