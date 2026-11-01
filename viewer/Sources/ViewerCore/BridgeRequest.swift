import Foundation

public enum BridgeFraming: Equatable {
    case incomplete, invalid, complete
}

public struct BridgeRequest {
    public static let maxHeaderBytes = 8192
    // 4096 presses (shift is part of each report), 4096 releases, final release.
    public static let maxKeyboardReports = 4096 * 2 + 1
    // Base64 of eight-byte reports plus a bounded JSON envelope.
    public static let maxBodyBytes = ((maxKeyboardReports * 8 + 2) / 3) * 4 + 128
    public static func keyboardReports(_ body: Data) -> [[UInt8]]? {
        guard let object = try? JSONSerialization.jsonObject(with: body) as? [String: String],
              let encoded = object["keyboard_base64"], let bytes = Data(base64Encoded: encoded),
              bytes.count % 8 == 0, bytes.count <= maxKeyboardReports * 8 else { return nil }
        return stride(from: 0, to: bytes.count, by: 8).map { Array(bytes[$0..<$0+8]) }
    }
    public let method: String
    public let target: String
    public let body: Data

    private static func header(_ data: Data) -> (String, String, [String: String], Data.Index)? {
        guard let end = data.range(of: Data("\r\n\r\n".utf8)),
              data.distance(from: data.startIndex, to: end.upperBound) <= maxHeaderBytes,
              let head = String(data: data[..<end.lowerBound], encoding: .utf8),
              let line = head.components(separatedBy: "\r\n").first else { return nil }
        let first = line.split(separator: " ")
        guard first.count == 3, first[2] == "HTTP/1.1",
              ["GET", "POST"].contains(first[0]), first[1].hasPrefix("/") else { return nil }
        var headers: [String: String] = [:]
        for line in head.components(separatedBy: "\r\n").dropFirst() {
            let parts = line.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
            guard parts.count == 2, !parts[0].isEmpty,
                  parts[0].allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-") }) else { return nil }
            let key = parts[0].lowercased()
            guard headers[key] == nil else { return nil }
            headers[key] = parts[1].trimmingCharacters(in: .whitespaces)
        }
        guard headers["transfer-encoding"] == nil else { return nil }
        return (String(first[0]), String(first[1]), headers, end.upperBound)
    }

    public static func framing(_ data: Data) -> BridgeFraming {
        guard data.count <= maxHeaderBytes + maxBodyBytes else { return .invalid }
        guard data.range(of: Data("\r\n\r\n".utf8)) != nil else {
            return data.count >= maxHeaderBytes ? .invalid : .incomplete
        }
        guard let (method, _, headers, bodyStart) = header(data) else { return .invalid }
        if method == "POST", headers["content-length"] == nil { return .invalid }
        let value = headers["content-length"] ?? "0"
        guard !value.isEmpty, value.utf8.allSatisfy({ (48...57).contains($0) }),
              let length = Int(value), length <= maxBodyBytes else { return .invalid }
        let received = data.distance(from: bodyStart, to: data.endIndex)
        if received > length { return .invalid }
        return received == length ? .complete : .incomplete
    }

    public init?(_ data: Data, token: String) {
        guard Self.framing(data) == .complete,
              let (method, target, headers, bodyStart) = Self.header(data),
              headers["authorization"] == "Bearer \(token)" else { return nil }
        self.method = method; self.target = target; body = Data(data[bodyStart...])
    }
}
