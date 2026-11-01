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
}
