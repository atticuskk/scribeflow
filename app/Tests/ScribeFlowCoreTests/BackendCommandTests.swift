import XCTest
@testable import ScribeFlowCore

final class BackendCommandTests: XCTestCase {
    func testConvertArguments() {
        var options = ConversionOptions()
        options.overwrite = true
        options.chapterLevel = 2
        options.crossPageMerge = false
        options.keepOCROutput = false
        let command = BackendCommand.convert(
            input: URL(fileURLWithPath: "/书/民法 讲义.pdf"),
            output: URL(fileURLWithPath: "/书/民法 讲义-Markdown"),
            options: options
        )
        XCTAssertEqual(command.arguments, [
            "-m", "scribeflow", "convert", "/书/民法 讲义.pdf", "--output", "/书/民法 讲义-Markdown",
            "--segment-pages", "16", "--lang", "ch", "--model-source", "modelscope",
            "--overwrite", "--discard-ocr-output", "--chapter-level", "2", "--no-cross-page-merge",
            "--events", "jsonl",
        ])
        XCTAssertEqual(command.environment, [:])
    }

    func testAIKeyGoesToEnvironmentNotArguments() {
        var options = ConversionOptions()
        options.ai = AIOptions(model: "gpt-test", baseURL: " https://example.com/v1 ", apiKey: "sk-secret")
        let command = BackendCommand.reprocess(output: URL(fileURLWithPath: "/out"), options: options)
        XCTAssertEqual(command.arguments, [
            "-m", "scribeflow", "reprocess", "/out",
            "--ai", "--ai-model", "gpt-test", "--ai-base-url", "https://example.com/v1",
            "--events", "jsonl",
        ])
        XCTAssertFalse(command.arguments.contains("sk-secret"))
        XCTAssertEqual(command.environment, ["SCRIBEFLOW_AI_API_KEY": "sk-secret"])
    }
}
