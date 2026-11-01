public struct VideoFormat {
    public struct RateRange {
        public let min: Double
        public let max: Double
        public init(min: Double, max: Double) { self.min = min; self.max = max }
    }
    public let width: Int32
    public let height: Int32
    public let subtype: UInt32
    public let ranges: [RateRange]
    public init(width: Int32, height: Int32, subtype: UInt32, ranges: [RateRange]) {
        self.width = width; self.height = height; self.subtype = subtype; self.ranges = ranges
    }
    // Return indices so the caller can use the exact native format and duration range.
    public static func select(_ formats: [VideoFormat]) -> (format: Int, range: Int)? {
        for (width, height): (Int32, Int32) in [(1920, 1080), (1280, 720)] {
            let candidates = formats.indices.filter { formats[$0].width == width && formats[$0].height == height }
            for index in candidates.filter({ formats[$0].subtype == 0x34323076 }) + candidates.filter({ formats[$0].subtype != 0x34323076 }) {
                if let range = formats[index].ranges.firstIndex(where: {
                    $0.min.isFinite && $0.max.isFinite && $0.min > 0 && $0.min <= $0.max && $0.min - 0.5 <= 30 && 30 <= $0.max + 0.5
                }) { return (index, range) }
            }
        }
        return nil
    }
}
