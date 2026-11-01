import Foundation
import Network
import AppKit
import CoreImage
import ViewerCore

final class Bridge: @unchecked Sendable {
    let serial: SerialWriter
    let frames: LatestFrameBuffer
    let token = UUID().uuidString + UUID().uuidString
    let queue = DispatchQueue(label: "kvm.bridge")
    var listener: NWListener?
    var activity: (@Sendable (Bool) -> Void)?
    init(serial: SerialWriter, frames: LatestFrameBuffer) { self.serial = serial; self.frames = frames }
    func start() throws {
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: .any)
        let listener = try NWListener(using: parameters)
        self.listener = listener
        listener.stateUpdateHandler = { [self] state in
            if case .ready = state, let port = listener.port {
                do {
                    let directory = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".kvmuse")
                    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
                    let data = try JSONSerialization.data(withJSONObject: ["port": Int(port.rawValue), "token": token])
                    let path = directory.appendingPathComponent("bridge.json")
                    let temporary = directory.appendingPathComponent(UUID().uuidString)
                    guard FileManager.default.createFile(atPath: temporary.path, contents: data, attributes: [.posixPermissions: 0o600]) else { return }
                    if rename(temporary.path, path.path) != 0 { try? FileManager.default.removeItem(at: temporary) }
                } catch { NSLog("Bridge discovery could not be written: %@", error.localizedDescription) }
            }
        }
        listener.newConnectionHandler = { [self] connection in
            connection.start(queue: queue)
            queue.asyncAfter(deadline: .now() + 30) { connection.cancel() }
            receive(connection, data: Data())
        }
        listener.start(queue: queue)
    }
    func receive(_ connection: NWConnection, data: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [self] chunk, _, done, error in
            var data = data; data.append(chunk ?? Data())
            guard data.count <= 524288 else { reply(connection, code: 413, text: "Request too large"); return }
            if let end = data.range(of: Data("\r\n\r\n".utf8)),
               let head = String(data: data[..<end.lowerBound], encoding: .utf8) {
                let lengths = head.components(separatedBy: "\r\n").filter { $0.lowercased().hasPrefix("content-length:") }
                let length = lengths.first.flatMap { Int($0.split(separator: ":", maxSplits: 1)[1].trimmingCharacters(in: .whitespaces)) } ?? 0
                if data.count >= end.upperBound + length {
                    guard let request = BridgeRequest(data, token: token) else { reply(connection, code: 400, text: "Invalid request or bridge token"); return }
                    handle(connection, request); return
                }
            }
            if done || error != nil { connection.cancel() } else { receive(connection, data: data) }
        }
    }
    func reply(_ connection: NWConnection, code: Int = 200, text: String) { reply(connection, code: code, data: Data(text.utf8), type: "text/plain") }
    func reply(_ connection: NWConnection, code: Int = 200, data: Data, type: String) {
        let header = "HTTP/1.1 \(code) Result\r\nContent-Type: \(type)\r\nContent-Length: \(data.count)\r\nConnection: close\r\n\r\n"
        connection.send(content: Data(header.utf8) + data, completion: .contentProcessed { _ in connection.cancel() })
    }
    func handle(_ connection: NWConnection, _ request: BridgeRequest) {
        let url = URLComponents(string: request.target)
        if request.method == "GET", url?.path == "/status" {
            reply(connection, data: Data("{\"path\":\"bridge\",\"capture\":{\"available\":\(frames.read() != nil)}}".utf8), type: "application/json"); return
        }
        if request.method == "GET", url?.path == "/frame" {
            guard let frame = frames.read() else { reply(connection, code: 503, text: "No camera frame. Check Camera permission for KVM Viewer and the capture device."); return }
            var image = CIImage(cvPixelBuffer: frame)
            if let value = url?.queryItems?.first(where: { $0.name == "max_width" })?.value {
                guard let width = Double(value), width.isFinite, width >= 1, width <= 8192 else { reply(connection, code: 400, text: "Invalid max_width"); return }
                let scale = min(1, width / image.extent.width)
                image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
            }
            guard let cg = CIContext().createCGImage(image, from: image.extent),
                  let data = NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:]) else { reply(connection, code: 503, text: "Cannot encode camera frame"); return }
            reply(connection, data: data, type: "image/png"); return
        }
        guard request.method == "POST", ["/keys", "/text", "/mouse", "/wake"].contains(url?.path ?? "") else { reply(connection, code: 404, text: "Unknown endpoint"); return }
        var reports: [(UInt8, [UInt8])] = []
        if url?.path == "/wake" {
            reports = [(2,HID.keyboard([], modifiers: 2)), (2,HID.keyboard([], modifiers: 0)), (5,[1,0,1,0,0]), (5,[1,0,255,0,0])]
        } else {
            guard let object = try? JSONSerialization.jsonObject(with: request.body) as? [String: Any],
                  let values = object["reports"] as? [[Int]], values.count <= 8194 else { reply(connection, code: 400, text: "Expected HID reports"); return }
            for value in values {
                guard let command = value.first, [2,4,5].contains(command),
                      value.count == (command == 2 ? 9 : command == 4 ? 8 : 6),
                      value.allSatisfy({ (0...255).contains($0) }),
                      (url?.path == "/mouse" ? command != 2 : command == 2) else { reply(connection, code: 400, text: "Invalid HID report"); return }
                reports.append((UInt8(command), value.dropFirst().map(UInt8.init)))
            }
        }
        activity?(true)
        serial.sendBatch(reports) { [self] error in
            activity?(false)
            reply(connection, code: error == nil ? 200 : 503, text: error ?? "ok")
        }
    }
}
