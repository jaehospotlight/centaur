import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { readAgentPrompt } from "./lib/pi-spawn";
import { createReadTool, createLsTool, COMPACT_LIMITS, NORMAL_LIMITS } from "./read";
import { createEditFileTool } from "./edit-file";
import { createCreateFileTool } from "./create-file";
import { createGrepTool } from "./grep";
import { createGlobTool } from "./glob";
import { createBashTool } from "./bash";
import { createUndoEditTool } from "./undo-edit";
import { createFormatFileTool } from "./format-file";
import { createSkillTool } from "./skill";
import { createFinderTool } from "./finder";
import { createOracleTool } from "./oracle";
import { createTaskTool } from "./task";
import { createLibrarianTool } from "./librarian";
import { createCodeReviewTool } from "./code-review";
import { createLookAtTool } from "./look-at";
import { createReadWebPageTool } from "./read-web-page";
import { createWebSearchTool } from "./web-search";
import { createSearchSessionsTool } from "./search-sessions";
import { createReadSessionTool } from "./read-session";
import { createReadGithubTool } from "./read-github";
import { createSearchGithubTool } from "./search-github";
import { createListDirectoryGithubTool } from "./list-directory-github";
import { createListRepositoriesTool } from "./list-repositories";
import { createGlobGithubTool } from "./glob-github";
import { createCommitSearchTool } from "./commit-search";
import { createDiffTool } from "./diff";

export { withFileLock } from "./lib/mutex";
export {
  saveChange,
  loadChanges,
  revertChange,
  findLatestChange,
  simpleDiff,
} from "./lib/file-tracker";

export default function (pi: ExtensionAPI) {
  const limits = process.env.PI_READ_COMPACT ? COMPACT_LIMITS : NORMAL_LIMITS;

  // Core filesystem tools
  pi.registerTool(createReadTool(limits));
  pi.registerTool(createLsTool(limits));
  pi.registerTool(createEditFileTool());
  pi.registerTool(createCreateFileTool());
  pi.registerTool(createGrepTool());
  pi.registerTool(createGlobTool());
  pi.registerTool(createBashTool());
  pi.registerTool(createUndoEditTool());
  pi.registerTool(createFormatFileTool());

  // Sub-agent tools
  pi.registerTool(createSkillTool());
  pi.registerTool(
    createFinderTool({ systemPrompt: readAgentPrompt("agent.amp.finder.md") }),
  );
  pi.registerTool(
    createOracleTool({ systemPrompt: readAgentPrompt("agent.amp.oracle.md") }),
  );
  pi.registerTool(createTaskTool());
  pi.registerTool(
    createLibrarianTool({
      systemPrompt: readAgentPrompt("agent.amp.librarian.md"),
    }),
  );
  pi.registerTool(
    createCodeReviewTool({
      systemPrompt: readAgentPrompt("prompt.amp.code-review-system.md"),
      reportFormat: readAgentPrompt("prompt.amp.code-review-report.md"),
    }),
  );
  pi.registerTool(
    createLookAtTool({
      systemPrompt: readAgentPrompt("prompt.amp.look-at.md"),
    }),
  );
  pi.registerTool(
    createReadWebPageTool({
      systemPrompt: readAgentPrompt("prompt.amp.read-web-page.md"),
    }),
  );

  // Search/session tools
  pi.registerTool(createWebSearchTool());
  pi.registerTool(createSearchSessionsTool());
  pi.registerTool(createReadSessionTool());

  // GitHub tools
  pi.registerTool(createReadGithubTool());
  pi.registerTool(createSearchGithubTool());
  pi.registerTool(createListDirectoryGithubTool());
  pi.registerTool(createListRepositoriesTool());
  pi.registerTool(createGlobGithubTool());
  pi.registerTool(createCommitSearchTool());
  pi.registerTool(createDiffTool());
}
