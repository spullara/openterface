import XCTest
@testable import ViewerCore
final class VideoFormatTests: XCTestCase {
    func format(_ width: Int32, _ subtype: UInt32, _ rates: [Double]) -> VideoFormat {
        VideoFormat(width: width, height: width == 1920 ? 1080 : 720, subtype: subtype,
                    ranges: rates.map { .init(min: $0, max: $0) })
    }
    func testActualDeviceFormats() {
        let formats = [format(1920, 0x34323076, [60.000240,50,30.000030,20,10]),
                       format(1920, 2037741171, [10,5]),
                       format(1280, 0x34323076, [60.000240,50,30.000030,20,10]),
                       format(1280, 2037741171, [25,10])]
        let selection = VideoFormat.select(formats)
        XCTAssertEqual(selection?.format, 0)
        XCTAssertEqual(selection?.range, 2)
        XCTAssertEqual(VideoFormat.select(Array(formats.dropFirst()))?.format, 1)
        XCTAssertNil(VideoFormat.select([formats[1]]))
        XCTAssertNil(VideoFormat.select([formats[3]]))
    }
    func testResolutionAndSubtypePreference() {
        let formats = [format(1280, 0x34323076, [30]), format(1920, 2037741171, [30]), format(1920, 0x34323076, [30.000030])]
        XCTAssertEqual(VideoFormat.select(formats)?.format, 2)
        XCTAssertEqual(VideoFormat.select(Array(formats.prefix(2)))?.format, 1)
        XCTAssertNil(VideoFormat.select([format(1920, 0x34323076, [31])]))
    }
}
