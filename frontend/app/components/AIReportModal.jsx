"use client";
import React, { useState } from "react";
import ReactMarkdown from "react-markdown";

export default function AIReportModal({
  isOpen,
  onClose,
  fundData,
  useBackend = false,
}) {
  const [aiResponse, setAiResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const generateReport = async () => {
    setLoading(true);
    setError(null);
    setAiResponse(null);

    try {
      // Determine which endpoint to use
      const endpoint = useBackend
        ? "/api/backend/ai/report"
        : "/api/ai/generate-report";
      const requestOptions = {
        method: useBackend ? "GET" : "POST",
        headers: {
          "Content-Type": "application/json",
        },
      };

      // Only add body for POST requests (frontend AI)
      if (!useBackend) {
        requestOptions.body = JSON.stringify({ fundData });
      }

      const response = await fetch(endpoint, requestOptions);

      if (!response.ok) {
        throw new Error("Failed to generate report");
      }

      // For backend endpoints, parse JSON response
      if (useBackend) {
        const data = await response.json();
        setAiResponse(data);
      } else {
        // For frontend endpoints, accumulate streaming text
        let report = "";
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value);
          report += chunk;
        }

        // Treat frontend response as plain text
        setAiResponse({ text: report, format: "plain" });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (isOpen && !aiResponse && !loading) {
      generateReport();
    }
  }, [isOpen]);

  const downloadReport = () => {
    if (!aiResponse) return;
    const element = document.createElement("a");
    const file = new Blob([aiResponse.text], { type: "text/plain" });
    element.href = URL.createObjectURL(file);
    element.download = `${fundData.meta?.scheme_name || "report"}-AI-Report.txt`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const copyToClipboard = () => {
    if (!aiResponse) return;
    navigator.clipboard.writeText(aiResponse.text);
    alert("Report copied to clipboard!");
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-[#181f31] rounded-2xl max-w-5xl w-full max-h-[90vh] overflow-hidden shadow-2xl border border-gray-700">
        {/* Header */}
        <div className="bg-gradient-to-r from-purple-600 to-pink-600 p-6 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <svg
              className="w-8 h-8 text-white"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <div>
              <h2 className="text-2xl font-bold text-white">
                AI Investment Report
              </h2>
              <p className="text-purple-100 text-sm">
                {useBackend
                  ? "Portfolio Analysis & Insights"
                  : "Comprehensive Analysis & Insights"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-white hover:bg-white/20 rounded-lg p-2 transition-colors"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-200px)]">
          {loading && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="animate-spin border-4 border-purple-400 border-t-transparent rounded-full w-12 h-12 mb-4"></div>
              <p className="text-gray-400 text-lg">
                Generating comprehensive report... 📊
              </p>
              <p className="text-gray-500 text-sm mt-2">
                This may take a moment
              </p>
            </div>
          )}

          {error && (
            <div className="bg-red-900/30 border border-red-600 rounded-lg p-4 text-red-400">
              <p className="font-semibold">Error: {error}</p>
              <button
                onClick={generateReport}
                className="mt-3 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm"
              >
                Try Again
              </button>
            </div>
          )}

          {aiResponse && (
            <div className="bg-[#232b44] rounded-lg p-6 text-white">
              {aiResponse.format === "markdown" ? (
                <ReactMarkdown
                  className="prose prose-invert max-w-none"
                  components={{
                    p: ({ node, ...props }) => (
                      <p
                        className="text-gray-100 leading-relaxed my-2"
                        {...props}
                      />
                    ),
                    h1: ({ node, ...props }) => (
                      <h1
                        className="text-2xl font-bold text-purple-300 mt-5 mb-3"
                        {...props}
                      />
                    ),
                    h2: ({ node, ...props }) => (
                      <h2
                        className="text-xl font-bold text-pink-300 mt-4 mb-2"
                        {...props}
                      />
                    ),
                    h3: ({ node, ...props }) => (
                      <h3
                        className="text-lg font-semibold text-purple-200 mt-3 mb-2"
                        {...props}
                      />
                    ),
                    h4: ({ node, ...props }) => (
                      <h4
                        className="text-base font-semibold text-pink-200 mt-2 mb-1"
                        {...props}
                      />
                    ),
                    ul: ({ node, ...props }) => (
                      <ul className="list-disc pl-6 my-2" {...props} />
                    ),
                    ol: ({ node, ...props }) => (
                      <ol className="list-decimal pl-6 my-2" {...props} />
                    ),
                    li: ({ node, ...props }) => (
                      <li className="text-gray-100 mb-1" {...props} />
                    ),
                    strong: ({ node, ...props }) => (
                      <strong className="font-bold text-pink-200" {...props} />
                    ),
                    em: ({ node, ...props }) => (
                      <em className="italic text-gray-200" {...props} />
                    ),
                    blockquote: ({ node, ...props }) => (
                      <blockquote
                        className="border-l-4 border-purple-500 pl-4 my-2 italic text-gray-300"
                        {...props}
                      />
                    ),
                    code: ({ node, inline, ...props }) =>
                      inline ? (
                        <code
                          className="bg-[#1a1f2e] px-2 py-1 rounded text-pink-300"
                          {...props}
                        />
                      ) : (
                        <code
                          className="bg-[#1a1f2e] p-3 rounded block text-pink-300 overflow-x-auto"
                          {...props}
                        />
                      ),
                  }}
                >
                  {aiResponse.text}
                </ReactMarkdown>
              ) : (
                <p className="text-gray-100 whitespace-pre-line leading-relaxed">
                  {aiResponse.text}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer with Actions */}
        <div className="bg-[#0d1020] p-4 flex justify-between items-center border-t border-gray-700 flex-wrap gap-3">
          <p className="text-gray-400 text-sm">
            📋 Professional AI-generated investment report
          </p>
          <div className="flex gap-3">
            {aiResponse && (
              <>
                <button
                  onClick={copyToClipboard}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-semibold transition-colors flex items-center gap-2 text-sm"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                    />
                  </svg>
                  Copy
                </button>
                <button
                  onClick={downloadReport}
                  className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-semibold transition-colors flex items-center gap-2 text-sm"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Download
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="bg-purple-600 hover:bg-purple-700 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
