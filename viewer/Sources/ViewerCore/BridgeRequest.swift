import Foundation

public struct BridgeRequest {
    public let method: String
    public let target: String
    public let body: Data
    public init?(_ data: Data, token: String) {
        guard let end = data.range(of: Data("\r\n\r\n".utf8)),
              let head = String(data: data[..<end.lowerBound], encoding: .utf8) else { return nil }
        let lines = head.components(separatedBy: "\r\n")
        let first = lines[0].split(separator: " ")
        guard first.count == 3 else { return nil }
        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            let parts = line.split(separator: ":", maxSplits: 1)
            guard parts.count == 2 else { return nil }
            let key = parts[0].lowercased()
            guard headers[key] == nil else { return nil }
            headers[key] = parts[1].trimmingCharacters(in: .whitespaces)
        }
        guard headers["authorization"] == "Bearer \(token)", headers["transfer-encoding"] == nil,
              let length = Int(headers["content-length"] ?? "0"), length >= 0,
              length == data.count - end.upperBound else { return nil }
        method = String(first[0]); target = String(first[1]); body = data[end.upperBound...]
    }
}
