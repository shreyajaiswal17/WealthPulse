"use client";
import React, { useState } from "react";
import ReactMarkdown from "react-markdown";

export default function AIDostModal({
  isOpen,
  onClose,
  fundData,
  useBackend = false,
}) {
  const [aiResponse, setAiResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const generateSummary = async () => {
    setLoading(true);
    setError(null);
    setAiResponse(null);

    try {
      // Determine which endpoint to use
      const endpoint = useBackend
        ? "/api/backend/ai/dost"
        : "/api/ai/summarize";
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
        throw new Error("Failed to generate summary");
      }

      // For backend endpoints, parse JSON response
      if (useBackend) {
        const data = await response.json();
        setAiResponse(data);
      } else {
        // For frontend endpoints, accumulate streaming text
        let summary = "";
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value);
          summary += chunk;
        }

        // Treat frontend response as plain text
        setAiResponse({ text: summary, format: "plain" });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (isOpen && !aiResponse && !loading) {
      generateSummary();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-[#181f31] rounded-2xl max-w-5xl w-full max-h-[90vh] overflow-hidden shadow-2xl border border-gray-700">
        {/* Header */}
        <div className="bg-gradient-to-r from-cyan-500 to-blue-600 p-6 flex justify-between items-center">
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
                d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
              />
            </svg>
            <h2 className="text-2xl font-bold text-white">
              AI Dost - Your Investment Buddy
            </h2>
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
              <div className="animate-spin border-4 border-cyan-400 border-t-transparent rounded-full w-12 h-12 mb-4"></div>
              <p className="text-gray-400 text-lg">
                AI Dost is analyzing{" "}
                {useBackend ? "your portfolio" : "the fund"}... 🤖
              </p>
            </div>
          )}

          {error && (
            <div className="bg-red-900/30 border border-red-600 rounded-lg p-4 text-red-400">
              <p className="font-semibold">Error: {error}</p>
              <button
                onClick={generateSummary}
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
                  className="prose prose-invert max-w-none prose-p:m-2 prose-h1:text-xl prose-h1:font-bold prose-h1:mt-4 prose-h1:mb-2 prose-h2:text-lg prose-h2:font-bold prose-h2:mt-3 prose-h2:mb-2 prose-ul:list-disc prose-ul:pl-4 prose-li:m-1"
                  components={{
                    p: ({ node, ...props }) => (
                      <p className="text-gray-100 leading-relaxed" {...props} />
                    ),
                    h1: ({ node, ...props }) => (
                      <h1
                        className="text-xl font-bold text-cyan-300 mt-4 mb-2"
                        {...props}
                      />
                    ),
                    h2: ({ node, ...props }) => (
                      <h2
                        className="text-lg font-bold text-cyan-400 mt-3 mb-2"
                        {...props}
                      />
                    ),
                    h3: ({ node, ...props }) => (
                      <h3
                        className="text-base font-semibold text-blue-300 mt-2 mb-1"
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
                      <strong className="font-bold text-cyan-200" {...props} />
                    ),
                    em: ({ node, ...props }) => (
                      <em className="italic text-gray-200" {...props} />
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

        {/* Footer */}
        <div className="bg-[#0d1020] p-4 flex justify-between items-center border-t border-gray-700">
          <p className="text-gray-400 text-sm">
            💡 This is AI-generated advice. Always do your own research!
          </p>
          <button
            onClick={onClose}
            className="bg-cyan-600 hover:bg-cyan-700 text-white px-6 py-2 rounded-lg font-semibold transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
