"use client";

import { useCallback, useState } from "react";
import dynamic from "next/dynamic";
import { Button } from "@/app/components/Button";
import { useTheme } from "@/app/context/ThemeContext";
import { executeCode } from "@/lib/api";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

const LANGUAGES = [
  { id: "python", label: "Python", monaco: "python" },
  { id: "javascript", label: "JavaScript", monaco: "javascript" },
  { id: "java", label: "Java", monaco: "java" },
  { id: "cpp", label: "C++", monaco: "cpp" },
  { id: "go", label: "Go", monaco: "go" },
  { id: "rust", label: "Rust", monaco: "rust" },
  { id: "typescript", label: "TypeScript", monaco: "typescript" },
  { id: "csharp", label: "C#", monaco: "csharp" },
  { id: "kotlin", label: "Kotlin", monaco: "kotlin" },
] as const;

const DEFAULT_CODE: Record<string, string> = {
  python: `# Read from stdin, write to stdout
# Example: nums = list(map(int, input().split()))
def main():
    line = input()
    # Your solution here
    print(line)

if __name__ == "__main__":
    main()
`,
  javascript: `// Read from stdin (Node.js)
const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin });

let input = [];
rl.on('line', (line) => input.push(line));
rl.on('close', () => {
  // Your solution here
  console.log(input.join('\\n'));
});
`,
  java: `import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        // Your solution here
        while (sc.hasNextLine()) {
            System.out.println(sc.nextLine());
        }
        sc.close();
    }
}
`,
  cpp: `#include <iostream>
using namespace std;

int main() {
    string line;
    while (getline(cin, line)) {
        // Your solution here
        cout << line << endl;
    }
    return 0;
}
`,
  go: `package main

import (
    "bufio"
    "fmt"
    "os"
)

func main() {
    scanner := bufio.NewScanner(os.Stdin)
    for scanner.Scan() {
        // Your solution here
        fmt.Println(scanner.Text())
    }
}
`,
  rust: `use std::io::{self, BufRead};

fn main() {
    let stdin = io::stdin();
    for line in stdin.lock().lines() {
        if let Ok(l) = line {
            // Your solution here
            println!("{}", l);
        }
    }
}
`,
  typescript: `// Run as Node.js with ts-node or compile to JS
const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin });

let input: string[] = [];
rl.on('line', (line: string) => input.push(line));
rl.on('close', () => {
  console.log(input.join('\\n'));
});
`,
  csharp: `using System;

class Program {
    static void Main() {
        string line;
        while ((line = Console.ReadLine()) != null) {
            Console.WriteLine(line);
        }
    }
}
`,
  kotlin: 'import java.util.Scanner\n\nfun main() {\n    val sc = Scanner(System.`in`)\n    while (sc.hasNextLine()) {\n        println(sc.nextLine())\n    }\n}',
};

export type TestCase = { input: string; expected: string };

type CodingPlaygroundProps = {
  testCases: TestCase[];
  onCodeChange?: (code: string) => void;
  onSubmitCode?: (code: string) => void;
  initialCode?: string;
};

export function CodingPlayground({
  testCases,
  onCodeChange,
  onSubmitCode,
  initialCode,
}: CodingPlaygroundProps) {
  const [language, setLanguage] = useState("python");
  const [code, setCode] = useState(
    initialCode ?? DEFAULT_CODE[language] ?? DEFAULT_CODE.python,
  );
  const { theme } = useTheme();
  const [runResult, setRunResult] = useState<{
    type: "run" | "submit";
    passed: number;
    failed: number;
    results: Array<{
      index: number;
      passed: boolean;
      input: string;
      expected: string;
      actual: string;
      error?: string;
    }>;
  } | null>(null);
  const [loading, setLoading] = useState(false);

  const langConfig = LANGUAGES.find((l) => l.id === language) ?? LANGUAGES[0];

  const handleLanguageChange = useCallback(
    (newLang: string) => {
      setLanguage(newLang);
      setCode(DEFAULT_CODE[newLang] ?? DEFAULT_CODE.python);
      setRunResult(null);
    },
    [],
  );

  const runTests = useCallback(
    async (casesToRun: TestCase[], type: "run" | "submit") => {
      if (casesToRun.length === 0) {
        setRunResult({
          type,
          passed: 0,
          failed: 0,
          results: [],
        });
        return;
      }

      setLoading(true);
      setRunResult(null);

      const results: Array<{
        index: number;
        passed: boolean;
        input: string;
        expected: string;
        actual: string;
        error?: string;
      }> = [];

      for (let i = 0; i < casesToRun.length; i++) {
        const tc = casesToRun[i];
        try {
          const res = await executeCode({
            language,
            code,
            stdin: tc.input,
          });

          const actual = (res.stdout || "").trim();
          const expected = (tc.expected || "").trim();
          const passed = actual === expected;

          results.push({
            index: i + 1,
            passed,
            input: tc.input,
            expected,
            actual: res.stderr ? `${actual}\n[stderr]\n${res.stderr}` : actual,
            error: res.run_error ?? undefined,
          });
        } catch (e) {
          results.push({
            index: i + 1,
            passed: false,
            input: tc.input,
            expected: tc.expected,
            actual: "",
            error: (e as Error).message,
          });
        }
      }

      const passed = results.filter((r) => r.passed).length;
      const failed = results.length - passed;

      setRunResult({
        type,
        passed,
        failed,
        results,
      });
      setLoading(false);
    },
    [language, code, onSubmitCode],
  );

  const handleRun = useCallback(() => {
    const sample = testCases.slice(0, 2);
    runTests(sample.length > 0 ? sample : testCases, "run");
  }, [testCases, runTests]);

  const handleRunAll = useCallback(() => {
    runTests(testCases, "submit");
  }, [testCases, runTests]);

  const handleEditorChange = useCallback(
    (value: string | undefined) => {
      const v = value ?? "";
      setCode(v);
      onCodeChange?.(v);
    },
    [onCodeChange],
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm font-medium">Language</label>
        <select
          value={language}
          onChange={(e) => handleLanguageChange(e.target.value)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
        >
          {LANGUAGES.map((l) => (
            <option key={l.id} value={l.id}>
              {l.label}
            </option>
          ))}
        </select>
      </div>

      <div className="min-h-[320px] overflow-hidden rounded-lg border border-slate-300 dark:border-slate-700">
        <MonacoEditor
          height="320px"
          language={langConfig.monaco}
          value={code}
          onChange={handleEditorChange}
          theme={theme === "dark" ? "vs-dark" : "light"}
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            padding: { top: 12 },
            scrollBeyondLastLine: false,
          }}
        />
      </div>

      {testCases.length === 0 && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          No test cases from question. Submit for Evaluation to get AI feedback.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          onClick={handleRun}
          loading={loading}
          loadingLabel="Running..."
          disabled={testCases.length === 0}
        >
          Run (Sample)
        </Button>
        <Button
          variant="secondary"
          onClick={handleRunAll}
          loading={loading}
          loadingLabel="Running..."
          disabled={testCases.length === 0}
        >
          Run All Tests ({testCases.length})
        </Button>
        {onSubmitCode && (
          <Button
            variant="success"
            onClick={() => onSubmitCode(code)}
            loading={loading}
            loadingLabel="Submitting..."
          >
            Submit for Evaluation
          </Button>
        )}
      </div>

      {runResult && (
        <div className="rounded-lg border border-slate-300 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900">
          <h3 className="text-sm font-semibold">
            {runResult.type === "run" ? "Sample Run" : "All Tests"} —{" "}
            <span className="text-emerald-600 dark:text-emerald-400">
              {runResult.passed} passed
            </span>
            {runResult.failed > 0 && (
              <>
                {" "}
                /{" "}
                <span className="text-red-600 dark:text-red-400">
                  {runResult.failed} failed
                </span>
              </>
            )}
          </h3>
          <div className="mt-2 max-h-48 space-y-2 overflow-auto">
            {runResult.results.map((r) => (
              <div
                key={r.index}
                className={`rounded border p-2 text-xs ${
                  r.passed
                    ? "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/50"
                    : "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/50"
                }`}
              >
                <span className="font-medium">
                  Test {r.index}: {r.passed ? "✓ Passed" : "✗ Failed"}
                </span>
                {!r.passed && (
                  <pre className="mt-1 whitespace-pre-wrap break-words">
                    Input: {r.input}
                    Expected: {r.expected}
                    Actual: {r.actual}
                    {r.error && `Error: ${r.error}`}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
