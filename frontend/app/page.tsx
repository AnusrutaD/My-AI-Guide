"use client";

import { useMemo, useState } from "react";
import { Button } from "@/app/components/Button";
import { CodingPlayground } from "@/app/components/CodingPlayground";
import type { TestCase } from "@/app/components/CodingPlayground";
import { ThemeToggle } from "@/app/components/ThemeToggle";
import {
  fetchDailyStatus,
  fetchHealth,
  fetchSessionState,
  respondSession,
  startSession,
} from "@/lib/api";

const requirementTemplate = `# Requirement Doc

## 1) Clarified Requirements
- 

## 2) Assumptions
- 

## 3) Functional Scope
- 

## 4) Non-Functional Constraints
- Throughput:
- Latency:
- Availability:
- Consistency:
- Security/Compliance:

## 5) API Contract Sketch
- 

## 6) Data Model Sketch
- 

## 7) Edge Cases / Failure Modes
- 

## 8) Open Questions
- 
`;

export default function Home() {
  const [userId, setUserId] = useState("wa_10000000001");
  const [threadId, setThreadId] = useState("");
  const [question, setQuestion] = useState("Click 'Start Challenge' to generate a question.");
  const [answer, setAnswer] = useState("");
  const [clarifyInput, setClarifyInput] = useState("");
  const [requirementDoc, setRequirementDoc] = useState(requirementTemplate);
  const [feedback, setFeedback] = useState("No evaluation yet.");
  const [health, setHealth] = useState("Unknown");
  const [topic, setTopic] = useState("-");
  const [subtopic, setSubtopic] = useState("-");
  const [stage, setStage] = useState("-");
  const [questionType, setQuestionType] = useState<string>("CODING");
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);

  const canRespond = useMemo(
    () => Boolean(userId.trim() && threadId.trim()),
    [userId, threadId],
  );

  async function withLoading<T>(action: string, fn: () => Promise<T>) {
    setLoadingAction(action);
    try {
      return await fn();
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleHealth() {
    return withLoading("health", async () => {
      try {
        const data = await fetchHealth();
        setHealth(`${data.status.toUpperCase()} · ${data.checkpointer ?? "unknown"}`);
      } catch (e) {
        setHealth(`Unavailable · ${(e as Error).message}`);
      }
    });
  }

  async function handleStart() {
    return withLoading("start", async () => {
      try {
        const data = await startSession({
          user_id: userId.trim(),
          thread_id: threadId.trim() || undefined,
        });
        setThreadId(data.thread_id);
        setQuestion(data.question_text);
        setTopic(data.topic || "-");
        setSubtopic(data.subtopic || "-");
        setQuestionType(data.question_type || "CODING");
        setTestCases(
          (data.test_cases ?? []).map((tc) => ({
            input: tc.input ?? "",
            expected: tc.expected ?? "",
          })),
        );
        setStage("testing");
        setFeedback("Challenge generated. Ask clarifications or submit your solution.");
      } catch (e) {
        setFeedback(`Start failed: ${(e as Error).message}`);
      }
    });
  }

  async function handleHint() {
    if (!canRespond) return;
    return withLoading("hint", async () => {
      try {
        const data = await respondSession({
          user_id: userId.trim(),
          thread_id: threadId.trim(),
          response: "hint",
        });
        setFeedback(data.feedback);
      } catch (e) {
        setFeedback(`Hint failed: ${(e as Error).message}`);
      }
    });
  }

  async function handleClarify() {
    if (!canRespond) return;
    const questionText = clarifyInput.trim();
    if (!questionText) {
      setFeedback("Please type a clarification question first.");
      return;
    }
    return withLoading("clarify", async () => {
      try {
        const data = await respondSession({
          user_id: userId.trim(),
          thread_id: threadId.trim(),
          response: `clarify: ${questionText}`,
        });
        setFeedback(data.feedback);
      } catch (e) {
        setFeedback(`Clarification failed: ${(e as Error).message}`);
      }
    });
  }

  async function handleSubmit(submission?: string) {
    if (!canRespond) return;
    const toSubmit = (submission ?? answer).trim();
    if (!toSubmit) {
      setFeedback("Please add your solution before submitting.");
      return;
    }
    return withLoading("submit", async () => {
      try {
        const data = await respondSession({
          user_id: userId.trim(),
          thread_id: threadId.trim(),
          response: toSubmit,
        });
        setFeedback(data.feedback);
        setStage("idle");
      } catch (e) {
        setFeedback(`Submit failed: ${(e as Error).message}`);
      }
    });
  }

  async function handleDailyStatus() {
    return withLoading("status", async () => {
      try {
        const data = await fetchDailyStatus(userId.trim(), 24);
        setFeedback(JSON.stringify(data, null, 2));
      } catch (e) {
        setFeedback(`Daily status failed: ${(e as Error).message}`);
      }
    });
  }

  async function handleRefreshState() {
    if (!canRespond) return;
    return withLoading("refresh", async () => {
      try {
        const data = await fetchSessionState(threadId.trim(), userId.trim());
        setStage(data.interview_stage || "-");
        setTopic(data.current_topic || "-");
        setSubtopic(data.current_subtopic || "-");
        const latest = data.messages?.[data.messages.length - 1];
        if (latest?.content && typeof latest.content === "string") {
          setQuestion(latest.content);
        }
      } catch (e) {
        setFeedback(`Refresh failed: ${(e as Error).message}`);
      }
    });
  }

  return (
    <div className="min-h-screen bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 bg-slate-100/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight sm:text-xl">SDE-3 Mentor Workspace</h1>
            <p className="text-xs text-slate-500 sm:text-sm dark:text-slate-400">
              Next.js Phase 2 · challenge + clarifications + requirement doc + evaluation
            </p>
          </div>
          <div className="grid grid-cols-1 gap-2 text-sm sm:flex sm:items-center">
            <ThemeToggle />
            <Button
              variant="secondary"
              onClick={handleHealth}
              loading={loadingAction === "health"}
              loadingLabel="Checking..."
              className="px-3 py-2 text-xs sm:text-sm"
            >
              Check Health
            </Button>
            <span className="text-[11px] text-slate-600 sm:text-xs dark:text-slate-300">{health}</span>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-3 px-4 py-4 sm:gap-4 sm:px-6 sm:py-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 sm:p-4 dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-base font-semibold">Session Setup</h2>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <input
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="User ID"
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm transition-colors focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950 dark:focus:border-blue-400"
              />
              <input
                value={threadId}
                onChange={(e) => setThreadId(e.target.value)}
                placeholder="Thread ID (optional)"
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm transition-colors focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950 dark:focus:border-blue-400"
              />
            </div>
            <div className="mt-3 grid grid-cols-1 gap-2 sm:flex sm:flex-wrap">
              <Button
                variant="primary"
                onClick={handleStart}
                loading={loadingAction === "start"}
                loadingLabel="Starting..."
                className="w-full sm:w-auto"
              >
                Start Challenge
              </Button>
              <Button
                variant="secondary"
                onClick={handleRefreshState}
                disabled={!canRespond}
                loading={loadingAction === "refresh"}
                loadingLabel="Refreshing..."
                className="w-full sm:w-auto"
              >
                Refresh State
              </Button>
              <Button
                variant="secondary"
                onClick={handleDailyStatus}
                loading={loadingAction === "status"}
                loadingLabel="Loading..."
                className="w-full sm:w-auto"
              >
                Daily Status
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className="rounded border border-slate-300 px-2 py-1 dark:border-slate-700">topic: {topic}</span>
              <span className="rounded border border-slate-300 px-2 py-1 dark:border-slate-700">subtopic: {subtopic}</span>
              <span className="rounded border border-slate-300 px-2 py-1 dark:border-slate-700">stage: {stage}</span>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 sm:p-4 dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-base font-semibold">Current Question</h2>
            <pre className="mt-3 max-h-64 overflow-auto rounded border border-slate-300 bg-white p-3 text-[11px] whitespace-pre-wrap sm:max-h-72 sm:text-xs dark:border-slate-800 dark:bg-slate-950">
              {question}
            </pre>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 sm:p-4 dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-base font-semibold">Clarifications</h2>
            <input
              value={clarifyInput}
              onChange={(e) => setClarifyInput(e.target.value)}
              placeholder="e.g., What consistency level is expected for settlement writes?"
              className="mt-3 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm transition-colors focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950 dark:focus:border-blue-400"
            />
            <div className="mt-3 grid grid-cols-1 gap-2 sm:flex sm:flex-wrap">
              <Button
                variant="secondary"
                onClick={handleClarify}
                disabled={!canRespond}
                loading={loadingAction === "clarify"}
                loadingLabel="Asking..."
                className="w-full sm:w-auto"
              >
                Ask Clarification
              </Button>
              <Button
                variant="secondary"
                onClick={handleHint}
                disabled={!canRespond}
                loading={loadingAction === "hint"}
                loadingLabel="Fetching..."
                className="w-full sm:w-auto"
              >
                Ask Hint
              </Button>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 sm:p-4 dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-base font-semibold">
              {questionType === "CODING" ? "Coding Playground" : "Final Solution Submission"}
            </h2>
            {questionType === "CODING" ? (
              <div className="mt-3">
                <CodingPlayground
                  testCases={testCases}
                  onSubmitCode={(code) => handleSubmit(code)}
                />
              </div>
            ) : (
              <>
                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="Paste your system design / debugging answer..."
                  className="mt-3 min-h-36 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm transition-colors focus:border-blue-500 sm:min-h-44 dark:border-slate-700 dark:bg-slate-950 dark:focus:border-blue-400"
                />
                <Button
                  variant="success"
                  onClick={() => handleSubmit()}
                  disabled={!canRespond}
                  loading={loadingAction === "submit"}
                  loadingLabel="Submitting..."
                  className="mt-3 w-full sm:w-auto"
                >
                  Submit for Evaluation
                </Button>
              </>
            )}
          </div>
        </section>

        <section className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 sm:p-4 dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-base font-semibold">Requirement Doc Draft</h2>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Fill this before final submission. Use clarifications above to close open questions.
            </p>
            <textarea
              value={requirementDoc}
              onChange={(e) => setRequirementDoc(e.target.value)}
              className="mt-3 min-h-[320px] w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs transition-colors focus:border-blue-500 sm:min-h-[420px] dark:border-slate-700 dark:bg-slate-950 dark:focus:border-blue-400"
            />
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 sm:p-4 dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-base font-semibold">Feedback / Status Output</h2>
            <pre className="mt-3 max-h-[320px] overflow-auto rounded border border-slate-300 bg-white p-3 text-[11px] whitespace-pre-wrap sm:max-h-[420px] sm:text-xs dark:border-slate-800 dark:bg-slate-950">
              {feedback}
            </pre>
          </div>
        </section>
      </main>
    </div>
  );
}
