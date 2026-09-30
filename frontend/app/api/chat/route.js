import { NextResponse } from "next/server";
import Groq from "groq-sdk";
import { GoogleGenerativeAI } from "@google/generative-ai";

// Lazy-initialize clients (to ensure env vars are loaded)
let groqClient = null;
let geminiClient = null;

function getGroqClient() {
  if (!groqClient && process.env.GROQ_API_KEY) {
    groqClient = new Groq({ apiKey: process.env.GROQ_API_KEY });
  }
  return groqClient;
}

function getGeminiClient() {
  if (!geminiClient && process.env.GEMINI_API_KEY) {
    geminiClient = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
  }
  return geminiClient;
}

// Helper: Create Groq stream
async function createGroqStream(messages, options = {}) {
  const client = getGroqClient();
  if (!client) throw new Error("GROQ_API_KEY not configured");
  const completion = await client.chat.completions.create({
    model: "llama-3.3-70b-versatile",
    messages,
    stream: true,
    temperature: options.temperature ?? 0.7,
    max_tokens: options.max_tokens ?? 1024,
  });
  return completion;
}

// Helper: Create Gemini stream (format-normalized output)
async function createGeminiStream(messages, options = {}) {
  const client = getGeminiClient();
  if (!client) throw new Error("GEMINI_API_KEY not configured");
  const model = client.getGenerativeModel({
    model: "gemini-2.0-flash",
  });

  // Convert OpenAI-style messages to Gemini format
  // Note: Gemini doesn't support system role; prepend system as first user message
  let contents = messages.map((m) => ({
    role:
      m.role === "system" ? "user" : m.role === "assistant" ? "model" : "user",
    parts: [{ text: m.content }],
  }));

  const result = await model.generateContentStream({
    contents,
    generationConfig: {
      temperature: options.temperature ?? 0.7,
      maxOutputTokens: options.max_tokens ?? 1024,
    },
  });

  // Wrap Gemini stream into async iterator matching OpenAI chunk shape
  async function* iterator() {
    for await (const chunk of result.stream) {
      const text = chunk.text();
      if (!text) continue;
      yield {
        choices: [{ delta: { content: text } }],
      };
    }
  }

  return iterator();
}

// Helper: Try Groq first, fallback to Gemini
async function getModelStream(messages, options = {}) {
  if (process.env.GROQ_API_KEY) {
    try {
      console.log("Using Groq (primary)");
      const stream = await createGroqStream(messages, options);
      return { stream, provider: "groq" };
    } catch (err) {
      console.warn("Groq failed, falling back to Gemini:", err.message);
    }
  }

  if (!process.env.GEMINI_API_KEY) {
    throw new Error("No GEMINI_API_KEY configured");
  }
  console.log("Using Gemini (fallback)");
  const stream = await createGeminiStream(messages, options);
  return { stream, provider: "gemini" };
}

// Build system prompt based on currentPage and selectedItem
function buildSystemPrompt(currentPage = "home", selectedItem = null) {
  const baseInstructions = `
          ⚠️ CRITICAL RESPONSE FORMAT RULES - FOLLOW THESE EXACTLY:
          - ABSOLUTELY NEVER start a response with any number (1., 2., 3., etc.)
          - NEVER use numbered lists under any circumstance
          - NEVER include "1." or any digit followed by period at the start
          - NEVER use structured formatting like "1. Point", "2. Point"
          - NEVER use UPPERCASE headings or "Key Points" sections
          - Write in plain, natural conversational paragraphs only
          
          COMMUNICATION STYLE:
          - Chat like a knowledgeable, friendly friend - not a textbook or formal guide
          - Keep responses natural and conversational
          - Use simple language and relatable analogies
          - Keep responses concise - 2-4 sentences usually, longer only if asking for details
          - Respond in the same language the user writes in (Hindi, English, or Hinglish)
          - Use occasional emojis (sparingly) to keep it light and friendly
          
          CONTENT GUIDELINES:
          - Explain concepts using everyday analogies and examples
          - Focus on answering the specific question asked
          - Prioritize recent and reliable financial information
          - Always cite sources if using current market data or recent news
          - Be honest if you're uncertain about something
          - Avoid being overly cautious or formal`;

  let systemMessage = "";

  if (currentPage === "stock-detail" && selectedItem) {
    systemMessage = `You're a friendly stock analyst chatting on WealthPulse. The user is looking at ${selectedItem} stock and wants to understand it better. Answer their specific questions about ${selectedItem} - things like its performance, whether it's a good buy, recent news, and trends. Chat naturally like you're explaining it to a friend over coffee.${baseInstructions}`;
  } else if (currentPage === "stocks") {
    systemMessage = `You're a friendly stock market guide on WealthPulse. Help the user understand how to explore stocks, what different metrics mean, and general stock investing ideas. Chat conversationally like you're explaining it to someone interested in stocks for the first time.${baseInstructions}`;
  } else if (currentPage === "fund-detail" && selectedItem) {
    systemMessage = `You're a friendly mutual fund guide on WealthPulse. The user is looking at the ${selectedItem} fund. Explain how this specific fund works, its performance, risk level, and whether it might be good for them. Chat naturally like a knowledgeable friend would.${baseInstructions}`;
  } else if (currentPage === "mutual-funds") {
    systemMessage = `You're a friendly investment guide on WealthPulse explaining mutual funds. Help the user understand fund basics like SIP, NAV, different fund types, and how to pick a good fund. Chat conversationally and use simple examples.${baseInstructions}`;
  } else if (currentPage === "crypto-detail" && selectedItem) {
    systemMessage = `You're a friendly crypto analyst chatting on WealthPulse. The user is looking at ${selectedItem} cryptocurrency and wants to understand it better. Answer their specific questions about ${selectedItem} - things like its technology, price movements, whether it's a good investment, and market trends. Chat naturally like you're explaining it to a friend over coffee.${baseInstructions}`;
  } else if (currentPage === "crypto") {
    systemMessage = `You're a friendly cryptocurrency guide on WealthPulse. Help the user understand how to explore cryptocurrencies, what blockchain technology means, different crypto types, and general investing ideas. Chat conversationally like you're explaining it to someone interested in crypto for the first time.${baseInstructions}`;
  } else if (currentPage === "courses") {
    systemMessage = `You're a friendly financial education guide on WealthPulse learning center. Help the user understand investment concepts, financial literacy basics, and learning strategies for their financial goals. Answer questions about courses, explain trading and investing fundamentals, and provide educational guidance. Keep it conversational and encouraging for learners at all levels.${baseInstructions}`;
  } else {
    // Default to home/general assistance
    systemMessage = `You're a friendly assistant for WealthPulse, a personal finance app. Help the user understand what the app does, how it works, and answer their general investment questions. Keep it casual, warm, and easy to understand - like chatting with a knowledgeable friend.${baseInstructions}`;
  }

  return systemMessage;
}

export async function POST(request) {
  try {
    const { prompt, currentPage = "home", selectedItem, enableWebSearch = true } = await request.json();

    if (!prompt) {
      throw new Error("No prompt provided");
    }

    // Log API call attempt
    console.log(
      "Processing chat request with prompt:",
      prompt.substring(0, 100) + "...",
    );

    // Build dynamic system prompt based on page context
    const systemPrompt = buildSystemPrompt(currentPage, selectedItem);

    // Set system context for financial advisor role
    const messages = [
      {
        role: "system",
        content: systemPrompt,
      },
      { role: "user", content: prompt },
    ];

    // Get AI stream (Groq primary, Gemini fallback)
    const { stream: chatStream, provider } = await getModelStream(messages, {
      temperature: 1,
      max_tokens: 1024,
    });
    console.log("AI provider:", provider);
    return createStreamResponse(chatStream);

    // Helper function to create stream response
    function createStreamResponse(chatStream) {
      const stream = new ReadableStream({
        async start(controller) {
          try {
            for await (const chunk of chatStream) {
              const content = chunk.choices[0]?.delta?.content || "";
              if (content) {
                controller.enqueue(new TextEncoder().encode(content));
              }
            }
            controller.close();
          } catch (error) {
            console.error("Stream error:", error);
            controller.error(error);
          }
        },
      });

      return new Response(stream, {
        headers: {
          "Content-Type": "text/plain",
          "Cache-Control": "no-cache",
        },
      });
    }
  } catch (error) {
    console.error("Chat API error:", {
      message: error.message,
      name: error.name,
      stack: error.stack,
    });

    if (error.message === "No prompt provided") {
      return NextResponse.json(
        { error: "Please provide a question or message" },
        { status: 400 },
      );
    }

    if (error.message?.includes("401")) {
      return NextResponse.json(
        { error: "Authentication failed with the chat service" },
        { status: 401 },
      );
    }

    if (error.message?.includes("429")) {
      return NextResponse.json(
        { error: "Too many requests. Please try again later." },
        { status: 429 },
      );
    }

    // Handle web search specific errors
    if (error.message?.includes("web search")) {
      return NextResponse.json(
        { error: "Web search is temporarily unavailable. Try again later." },
        { status: 503 },
      );
    }

    return NextResponse.json(
      { error: error.message || "Failed to process chat request" },
      { status: 500 },
    );
  }
}
