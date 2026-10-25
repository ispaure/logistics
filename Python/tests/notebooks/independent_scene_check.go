// Independent, pinned remarquee reader for synthetic Logistics notebook exports.
package main

import (
 "archive/zip"
 "bytes"
 "encoding/json"
 "fmt"
 "io"
 "os"
 "strings"

 "github.com/go-go-golems/remarquee/pkg/rmdoc"
)

func main() {
 archive, err := zip.OpenReader(os.Args[1]); if err != nil { panic(err) }; defer archive.Close()
 members := map[string][]byte{}
 document := ""
 for _, member := range archive.File {
  stream, e := member.Open(); if e != nil { panic(e) }
  data, e := io.ReadAll(stream); stream.Close(); if e != nil { panic(e) }
  members[member.Name] = data
  if !strings.Contains(member.Name,"/") && strings.HasSuffix(member.Name,".content") { document = strings.TrimSuffix(member.Name,".content") }
 }
 _, _, pages, err := rmdoc.ParseContent(members[document+".content"]); if err != nil { panic(err) }
 counts := []int{}
 all := []rmdoc.Stroke{}
 for _, page := range pages {
  data := members[document+"/"+page.PageID+".rm"]
  if len(data)==0 { counts=append(counts,0);continue }
  tree, e := rmdoc.ParseRMV6SceneTree(bytes.NewReader(data)); if e != nil { panic(e) }
  strokes,e := rmdoc.ExtractRMV6StrokesWithAnchors(tree); if e != nil { panic(e) }
  counts=append(counts,len(strokes)); all=append(all,strokes...)
 }
 result := map[string]any{"reader":"remarquee v0.0.14","pages":len(pages),"stroke_counts":counts,"strokes":all}
 output,err:=json.Marshal(result);if err!=nil {panic(err)};fmt.Println(string(output))
}
