import XCTest
@testable import ViewerCore
final class BridgeRequestTests: XCTestCase {
    func testAuthenticationAndLength() {
        let request = "POST /wake HTTP/1.1\r\nAuthorization: Bearer secret\r\nContent-Length: 2\r\n\r\n{}"
        XCTAssertEqual(BridgeRequest(Data(request.utf8), token: "secret")?.target, "/wake")
        XCTAssertNil(BridgeRequest(Data(request.utf8), token: "wrong"))
        XCTAssertNil(BridgeRequest(Data(request.dropLast().utf8), token: "secret"))
        XCTAssertNil(BridgeRequest(Data("GET /status HTTP/1.1\r\n\r\n".utf8), token: "secret"))
    }
    func testBoundedFraming() {
        for value in ["", "abc", "-1", String(Int.max), String(BridgeRequest.maxBodyBytes + 1), "+2"] {
            let request = "POST /wake HTTP/1.1\r\nContent-Length: \(value)\r\n\r\n"
            XCTAssertEqual(BridgeRequest.framing(Data(request.utf8)), .invalid, value)
        }
        XCTAssertEqual(BridgeRequest.framing(Data("POST /wake HTTP/1.1\r\n\r\n".utf8)), .invalid)
        XCTAssertEqual(BridgeRequest.framing(Data("POST /wake HTTP/1.1\r\nContent-Length: 2\r\n\r\n{}".utf8)), .complete)
        XCTAssertEqual(BridgeRequest.framing(Data("POST /wake HTTP/1.1\r\nContent-Length: 2\r\n\r\n{".utf8)), .incomplete)
        XCTAssertEqual(BridgeRequest.framing(Data("POST /wake HTTP/1.1\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n".utf8)), .invalid)
        XCTAssertEqual(BridgeRequest.framing(Data(repeating: 65, count: 8192)), .invalid)
        XCTAssertEqual(BridgeRequest.framing(Data(("GET /status HTTP/1.1\r\nX: " + String(repeating: "a", count: 8192) + "\r\n\r\n").utf8)), .invalid)
        XCTAssertEqual(BridgeRequest.framing(Data("GET /status HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n".utf8)), .invalid)
    }
    func testMaximumKeyboardBody() throws {
        let bytes = Data(repeating: 2, count: BridgeRequest.maxKeyboardReports * 8)
        let body = try JSONSerialization.data(withJSONObject: ["keyboard_base64": bytes.base64EncodedString()])
        XCTAssertLessThanOrEqual(body.count, BridgeRequest.maxBodyBytes)
        let head = Data("POST /text HTTP/1.1\r\nContent-Length: \(body.count)\r\n\r\n".utf8)
        XCTAssertEqual(BridgeRequest.framing(head + body), .complete)
        XCTAssertEqual(BridgeRequest.keyboardReports(body)?.count, 8193)
        let oversized = try JSONSerialization.data(withJSONObject: ["keyboard_base64": (bytes + Data(repeating: 0, count: 8)).base64EncodedString()])
        XCTAssertNil(BridgeRequest.keyboardReports(oversized))
    }
}
