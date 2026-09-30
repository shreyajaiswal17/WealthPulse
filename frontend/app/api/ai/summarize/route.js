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

export async function POST(request) {
  try {
    const { fundData } = await request.json();

    // Check if this is portfolio data (multiple items) or single fund data
    const isPortfolio =
      fundData.portfolioItems && fundData.portfolioItems.length > 0;

    let fundInfo, prompt;

    if (isPortfolio) {
      // Portfolio context - analyze all holdings
      const stocksCount = fundData.meta?.stocks_count || 0;
      const mfCount = fundData.meta?.mutual_funds_count || 0;
      const cryptoCount =
        fundData.portfolioItems?.filter((i) => i.item_type === "crypto")
          .length || 0;

      // Build detailed portfolio items list
      const itemsList = fundData.portfolioItems
        .map((item, idx) => {
          const returnStr = item.risk_volatility?.annualized_return
            ? `${(item.risk_volatility.annualized_return * 100).toFixed(2)}%`
            : "N/A";
          const volatilityStr = item.risk_volatility?.annualized_volatility
            ? `${(item.risk_volatility.annualized_volatility * 100).toFixed(2)}%`
            : "N/A";
          const navStr = item.nav ? `₹${item.nav}` : "N/A";

          return `${idx + 1}. ${item.name} (${item.item_type})
   - Symbol: ${item.symbol || "N/A"}
   - Current Price/NAV: ${navStr}
   - Annual Return: ${returnStr}
   - Volatility: ${volatilityStr}
   - Added: ${new Date(item.added_at).toLocaleDateString()}`;
        })
        .join("\n\n");

      fundInfo = `
Portfolio Analysis:
- Total Holdings: ${fundData.meta?.portfolio_size || 0}
- Stocks: ${stocksCount}
- Mutual Funds: ${mfCount}
- Cryptocurrencies: ${cryptoCount}

Portfolio Performance Metrics:
- Average Annualized Return: ${((fundData.riskVolatility?.annualized_return || 0) * 100).toFixed(2)}%
- Average Volatility: ${((fundData.riskVolatility?.annualized_volatility || 0) * 100).toFixed(2)}%
- Sharpe Ratio: ${fundData.riskVolatility?.sharpe_ratio?.toFixed(2) || "N/A"}

Monte Carlo Portfolio Prediction (1 Year):
- Expected Portfolio Value: ₹${fundData.monteCarlo?.expected_nav?.toFixed(2) || "N/A"}
- Probability of Positive Return: ${fundData.monteCarlo?.probability_positive_return?.toFixed(2) || "N/A"}%

Your Holdings:
${itemsList}
`;

      prompt = `You are a friendly investment advisor called "AI Dost" (Dost means friend in Hindi). Analyze this PORTFOLIO (containing stocks, mutual funds, and/or cryptocurrencies) and explain it to a beginner investor in a very simple, friendly, and easy-to-understand way.

IMPORTANT FORMATTING INSTRUCTIONS:
- DO NOT use hash symbols (#) or asterisks (**) for headings
- Use simple text with emojis for sections (e.g., 🎯 Portfolio Overview)
- Use bullet points (•) or dashes (-) for all lists
- Keep it conversational and friendly
- Headings should be plain text with emojis, no special formatting

Focus on:

🎯 Portfolio Overview
• What mix of investments do they have?
• Overall composition

📈 Overall Performance
• How is the portfolio doing?
• Key performance indicators

💰 Diversification & Risk
• Is it well-balanced?
• Risk assessment

🔮 Future Outlook
• What to expect
• Predictions

👍 Should They Make Changes?
• Suggestions for improvement
• Action items

💡 Quick Tips for Portfolio Management
• Practical advice
• Best practices

Keep it short, friendly, and use emojis. Avoid jargon. Explain like talking to a friend over chai ☕

Portfolio Data:
${fundInfo}`;
    } else {
      // Single fund/stock context
      const currentNav =
        fundData.navHistory?.length > 0
          ? fundData.navHistory[fundData.navHistory.length - 1]?.nav
          : "N/A";
      const navDisplay =
        currentNav !== "N/A" ? `₹${parseFloat(currentNav).toFixed(2)}` : "N/A";

      fundInfo = `
Mutual Fund Analysis:
- Fund Name: ${fundData.meta?.scheme_name || fundData.meta?.schemeName || "Unknown"}
- Fund House: ${fundData.meta?.fund_house || fundData.meta?.amc || "Unknown"}
- Category: ${fundData.meta?.scheme_category || "Unknown"}
- Type: ${fundData.meta?.scheme_type || "Unknown"}

Performance Metrics:
- Annualized Return: ${((fundData.riskVolatility?.annualized_return || 0) * 100).toFixed(2)}%
- Annualized Volatility: ${((fundData.riskVolatility?.annualized_volatility || 0) * 100).toFixed(2)}%
- Sharpe Ratio: ${fundData.riskVolatility?.sharpe_ratio?.toFixed(2) || "N/A"}

Monte Carlo Prediction (1 Year):
- Expected NAV: ₹${fundData.monteCarlo?.expected_nav?.toFixed(2) || "N/A"}
- Probability of Positive Return: ${fundData.monteCarlo?.probability_positive_return?.toFixed(2) || "N/A"}%
- Range: ₹${fundData.monteCarlo?.lower_bound_5th_percentile?.toFixed(2) || "N/A"} - ₹${fundData.monteCarlo?.upper_bound_95th_percentile?.toFixed(2) || "N/A"}

Current NAV: ${navDisplay}
Total Historical Data Points: ${fundData.navHistory?.length || 0}
`;

      prompt = `You are a friendly investment advisor called "AI Dost" (Dost means friend in Hindi). Analyze this mutual fund data and explain it to a beginner investor in a very simple, friendly, and easy-to-understand way.

IMPORTANT FORMATTING INSTRUCTIONS:
- DO NOT use hash symbols (#) or asterisks (**) for headings
- Use simple text with emojis for sections (e.g., 🎯 What This Fund Is About)
- Use bullet points (•) or dashes (-) for all lists
- Keep it conversational and friendly
- Headings should be plain text with emojis, no special formatting

Focus on:

🎯 What This Fund Is About
• Simple explanation of the fund
• What it invests in

📈 How It Has Performed
• Good or bad performance?
• Why?

💰 Risk Level
• Is it safe or risky?
• Risk factors

🔮 Future Expectations
• What to expect
• Predictions

👍 Should You Consider It?
• Pros and cons
• Suitability

💡 Quick Tips for This Type of Fund
• Practical advice
• Best practices

Keep it short, friendly, and use emojis. Avoid jargon. Explain like talking to a friend over chai ☕

Fund Data:
${fundInfo}`;
    }

    // Get AI stream (Groq primary, Gemini fallback)
    const { stream: chatCompletion, provider } = await getModelStream(
      [
        {
          role: "user",
          content: prompt,
        },
      ],
      {
        temperature: 0.8,
        max_tokens: 1024,
      },
    );
    console.log("AI provider:", provider);

    // Create a readable stream for the response
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        try {
          for await (const chunk of chatCompletion) {
            const content = chunk.choices[0]?.delta?.content || "";
            if (content) {
              controller.enqueue(encoder.encode(content));
            }
          }
          controller.close();
        } catch (error) {
          controller.error(error);
        }
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Transfer-Encoding": "chunked",
      },
    });
  } catch (error) {
    console.error("Error in AI summarization:", error);
    return NextResponse.json(
      { error: "Failed to generate summary" },
      { status: 500 },
    );
  }
}
