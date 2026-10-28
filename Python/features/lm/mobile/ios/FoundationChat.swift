import Foundation
import FoundationModels

// Rubicon polls immutable snapshots; Foundation Models stays in its Swift task.
@objc(LogisticsFoundationChat)
final class LogisticsFoundationChat: NSObject, @unchecked Sendable {
    private let lock = NSLock()
    private var text = ""
    private var done = false
    private var error = ""
    private var task: Task<Void, Never>?

    @objc func availability() -> String {
        guard #available(iOS 26.0, *) else { return "Apple's on-device model requires iOS 26 or later." }
        switch SystemLanguageModel.default.availability {
        case .available: return "available"
        case .unavailable(.deviceNotEligible): return "This device does not support Apple Intelligence. iPhone 15 Pro or a newer supported device is required."
        case .unavailable(.appleIntelligenceNotEnabled): return "Turn on Apple Intelligence in Settings, then check again."
        case .unavailable(.modelNotReady): return "Apple Intelligence is preparing its model. Check again when it finishes."
        case .unavailable: return "Apple Intelligence is currently unavailable."
        }
    }

    private func publish(_ content: String? = nil, done: Bool = false, error: String = "") {
        lock.lock()
        defer { lock.unlock() }
        if let content { text = content }
        self.done = done
        self.error = error
    }

    @objc func snapshot() -> String {
        lock.lock()
        defer { lock.unlock() }
        let value: [String: Any] = ["text": text, "done": done, "error": error]
        return String(data: try! JSONSerialization.data(withJSONObject: value), encoding: .utf8)!
    }

    @objc func cancel() { task?.cancel() }

    @objc func startRequest(_ request: String) {
        task = Task {
            guard #available(iOS 26.0, *) else {
                publish(done: true, error: availability())
                return
            }
            do {
                let payload = try JSONSerialization.jsonObject(with: Data(request.utf8)) as! [String: Any]
                let messages = payload["messages"] as! [[String: String]]
                var entries: [Transcript.Entry] = []
                for message in messages.dropLast() {
                    let segments: [Transcript.Segment] = [.text(.init(content: message["content"]!))]
                    switch message["role"]! {
                    case "system": entries.append(.instructions(.init(segments: segments, toolDefinitions: [])))
                    case "user": entries.append(.prompt(.init(segments: segments)))
                    case "assistant": entries.append(.response(.init(assetIDs: [], segments: segments)))
                    default: break
                    }
                }
                let session = LanguageModelSession(transcript: Transcript(entries: entries))
                let options = GenerationOptions(maximumResponseTokens: payload["max_tokens"] as? Int)
                for try await response in session.streamResponse(to: messages.last!["content"]!, options: options) {
                    try Task.checkCancellation()
                    if response.content.utf8.count > 256 * 1024 {
                        publish(done: true, error: "Reply exceeds the mobile 256 KiB limit.")
                        return
                    }
                    publish(response.content)
                }
                publish(done: true)
            } catch is CancellationError {
                publish(done: true, error: "Request cancelled.")
            } catch {
                // Keep prompt/transcript contents out of diagnostics.
                publish(done: true, error: "Apple Intelligence could not complete the reply. Try a shorter conversation or check language, availability and content restrictions.")
            }
        }
    }
}
