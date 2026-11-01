import XCTest
@testable import ViewerCore
final class HIDTests: XCTestCase {
    func testPackets() {
        XCTAssertEqual(HID.packet(2, [0,0,4,0,0,0,0,0]), [0x57,0xab,0,2,8,0,0,4,0,0,0,0,0,0x10])
        XCTAssertEqual(HID.packet(2, Array(repeating: 0, count: 8)).last, 12)
        XCTAssertEqual(HID.mouse(x: 1, y: 0, buttons: 2, wheel: -1), [2,2,255,15,0,0,255])
    }
    func testKeys() {
        for (code, usage): (UInt16, UInt8) in [(0,4),(36,40),(53,41),(48,43),(51,42),(123,80),(124,79),(125,81),(126,82),(122,58),(111,69)] { XCTAssertEqual(HID.usages[code], usage) }
        XCTAssertEqual(Set(HID.usages.values.filter { (4...29).contains($0) }).count, 26)
        XCTAssertEqual(HID.keyboard([4,5], modifiers: 15), [15,0,4,5,0,0,0,0])
    }
}
