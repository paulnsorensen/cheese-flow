import { spawn } from "node:child_process";
import { useEffect, useRef, useState } from "react";
import {
  ConfirmInput,
  MultiSelect,
  ProgressBar,
  Spinner,
  StatusMessage,
  TextInput,
} from "@inkjs/ui";
import { Box, Text, render, useApp } from "ink";
import { harnessAdapters } from "../adapters/index.js";
import type { HarnessName } from "../domain/harness.js";
import { runToolCheck, toolChecks } from "./doctor.js";
import type { ToolResult } from "./doctor.js";
import { installHarnessArtifacts } from "./compiler.js";

type Step =
  | "name"
  | "harness"
  | "checking"
  | "permission"
  | "installing"
  | "done";

type TaskStatus = "pending" | "running" | "done" | "error";
type Task = { label: string; status: TaskStatus };

const HARNESS_OPTIONS = Object.values(harnessAdapters).map((a) => ({
  label: a.displayName,
  value: a.name,
}));

function updateAt(tasks: Task[], index: number, status: TaskStatus): Task[] {
  return tasks.map((t, i) => (i === index ? { ...t, status } : t));
}

function runCommand(cmd: string, args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: "pipe" });
    child.on("error", reject);
    child.on("close", (code) =>
      code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}`)),
    );
  });
}

function Wizard({ projectRoot }: { projectRoot: string }) {
  const { exit } = useApp();
  const [step, setStep] = useState<Step>("name");
  const [userName, setUserName] = useState("");
  const [harnesses, setHarnesses] = useState<HarnessName[]>([]);
  const [missingTools, setMissingTools] = useState<ToolResult[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [progress, setProgress] = useState(0);
  const installingStarted = useRef(false);

  useEffect(() => {
    if (step !== "checking") return;
    void (async () => {
      const results = await Promise.all(toolChecks.map(runToolCheck));
      const missing = results.filter((r) => !r.ok && r.tier === "recommended");
      setMissingTools(missing);
      setStep(missing.length > 0 ? "permission" : "installing");
    })();
  }, [step]);

  useEffect(() => {
    if (step !== "installing" || installingStarted.current) return;
    installingStarted.current = true;

    const toolTasks: Task[] = missingTools.map((t) => ({
      label: `Install ${t.name}`,
      status: "pending",
    }));
    const harnessTasks: Task[] = harnesses.map((h) => ({
      label: `Compile ${harnessAdapters[h].displayName} bundle`,
      status: "pending",
    }));
    const all = [...toolTasks, ...harnessTasks];
    setTasks(all);

    void (async () => {
      let done = 0;
      const total = all.length;

      for (let i = 0; i < missingTools.length; i++) {
        setTasks((prev) => updateAt(prev, i, "running"));
        try {
          await runCommand("brew", ["install", missingTools[i]!.name]);
          setTasks((prev) => updateAt(prev, i, "done"));
        } catch {
          setTasks((prev) => updateAt(prev, i, "error"));
        }
        setProgress(Math.round((++done / total) * 100));
      }

      const offset = missingTools.length;
      for (let i = 0; i < harnesses.length; i++) {
        setTasks((prev) => updateAt(prev, offset + i, "running"));
        try {
          await installHarnessArtifacts({
            projectRoot,
            harnesses: [harnesses[i]!],
          });
          setTasks((prev) => updateAt(prev, offset + i, "done"));
        } catch {
          setTasks((prev) => updateAt(prev, offset + i, "error"));
        }
        setProgress(Math.round((++done / total) * 100));
      }

      setStep("done");
    })();
  }, [step, missingTools, harnesses, projectRoot]);

  useEffect(() => {
    if (step !== "done") return;
    const t = setTimeout(exit, 600);
    return () => clearTimeout(t);
  }, [step, exit]);

  if (step === "name") {
    return (
      <Box flexDirection="column" gap={1} paddingY={1}>
        <Text bold color="yellow">
          Welcome to cheese-flow setup!
        </Text>
        <Box gap={1}>
          <Text>What would you like to be called?</Text>
          <TextInput
            placeholder="Your name"
            onSubmit={(value) => {
              const trimmed = value.trim();
              if (trimmed) {
                setUserName(trimmed);
                setStep("harness");
              }
            }}
          />
        </Box>
      </Box>
    );
  }

  if (step === "harness") {
    return (
      <Box flexDirection="column" gap={1} paddingY={1}>
        <Text bold>
          Hey {userName}! Which harnesses should we install for?
        </Text>
        <Text dimColor>Space to toggle · Enter to confirm</Text>
        <MultiSelect
          options={HARNESS_OPTIONS}
          onSubmit={(values) => {
            if (values.length > 0) {
              setHarnesses(values as HarnessName[]);
              setStep("checking");
            }
          }}
        />
      </Box>
    );
  }

  if (step === "checking") {
    return (
      <Box paddingY={1}>
        <Spinner label="Checking tool dependencies..." />
      </Box>
    );
  }

  if (step === "permission") {
    return (
      <Box flexDirection="column" gap={1} paddingY={1}>
        <Text>These recommended tools are missing:</Text>
        <Box flexDirection="column" paddingLeft={2}>
          {missingTools.map((t) => (
            <Box key={t.name} gap={1}>
              <Text color="yellow">•</Text>
              <Text bold>{t.name}</Text>
              <Text dimColor>({t.installHint})</Text>
            </Box>
          ))}
        </Box>
        <Box gap={1}>
          <Text>May I run commands to install them?</Text>
          <ConfirmInput
            defaultChoice="cancel"
            onConfirm={() => setStep("installing")}
            onCancel={() => {
              setMissingTools([]);
              setStep("installing");
            }}
          />
        </Box>
      </Box>
    );
  }

  if (step === "installing") {
    return (
      <Box flexDirection="column" gap={1} paddingY={1}>
        <Text bold>Installing...</Text>
        <ProgressBar value={progress} />
        <Box flexDirection="column" marginTop={1}>
          {tasks.map((task, i) => (
            <Box key={i}>
              {task.status === "pending" && (
                <Text dimColor>  ○ {task.label}</Text>
              )}
              {task.status === "running" && (
                <Spinner label={`  ${task.label}`} />
              )}
              {task.status === "done" && (
                <StatusMessage variant="success">{task.label}</StatusMessage>
              )}
              {task.status === "error" && (
                <StatusMessage variant="error">
                  {task.label} — failed
                </StatusMessage>
              )}
            </Box>
          ))}
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" gap={1} paddingY={1}>
      <StatusMessage variant="success">
        All set, {userName}! cheese-flow is ready.
      </StatusMessage>
      <Box flexDirection="column" paddingLeft={2}>
        {harnesses.map((h) => (
          <Text key={h} dimColor>
            ✓ {harnessAdapters[h].displayName}
          </Text>
        ))}
      </Box>
    </Box>
  );
}

export async function runInitWizard(options: {
  projectRoot: string;
}): Promise<void> {
  const { waitUntilExit } = render(<Wizard projectRoot={options.projectRoot} />);
  await waitUntilExit();
}
