import XCTest
@testable import ViewerCore
final class ViewerStateTests: XCTestCase {
    func testDoubleTap() {
        var tap = DoubleTap()
        XCTAssertFalse(tap.press(at: 1))
        XCTAssertFalse(tap.press(at: 2))
        XCTAssertTrue(tap.press(at: 2.3))
        XCTAssertFalse(tap.press(at: 2.35))
        tap.reset()
        XCTAssertFalse(tap.press(at: 2.4))
    }
    func testBlackHint() {
        var hint = BlackFrameHint()
        XCTAssertFalse(hint.update(samples: [0, 16, 24], at: 1))
        XCTAssertFalse(hint.update(samples: [0, 0], at: 2.9))
        XCTAssertTrue(hint.update(samples: [0, 0], at: 3))
        XCTAssertFalse(hint.update(samples: [0, 100], at: 4))
        XCTAssertFalse(hint.update(samples: [0], at: 5))
        XCTAssertFalse(hint.update(samples: [], at: 8))
    }
}
