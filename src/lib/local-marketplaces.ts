import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import type { PluginMetadata } from "../domain/harness.js";

type MarketplaceInstallDetails = {
  marketplaceName: string;
  pluginName: string;
};

function marketplaceName(pluginName: string): string {
  return `${pluginName}-local`;
}

async function writeJsonFile(
  filePath: string,
  payload: Record<string, unknown>,
): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

export async function writeClaudeMarketplace(
  bundleRoot: string,
  metadata: PluginMetadata,
): Promise<MarketplaceInstallDetails> {
  const details = {
    marketplaceName: marketplaceName(metadata.name),
    pluginName: metadata.name,
  };
  await writeJsonFile(
    path.join(bundleRoot, ".claude-plugin", "marketplace.json"),
    {
      name: details.marketplaceName,
      owner: {
        name: metadata.author.name,
        ...(metadata.author.email !== undefined
          ? { email: metadata.author.email }
          : {}),
      },
      plugins: [
        {
          name: metadata.name,
          source: "./",
          description: metadata.description,
          version: metadata.version,
          author: metadata.author,
          repository: metadata.repository,
          ...(metadata.homepage !== undefined
            ? { homepage: metadata.homepage }
            : {}),
          ...(metadata.keywords !== undefined
            ? { keywords: metadata.keywords }
            : {}),
          strict: true,
        },
      ],
    },
  );
  return details;
}

export async function writeCodexMarketplace(
  bundleRoot: string,
  metadata: PluginMetadata,
): Promise<MarketplaceInstallDetails> {
  const details = {
    marketplaceName: marketplaceName(metadata.name),
    pluginName: metadata.name,
  };
  await writeJsonFile(
    path.join(bundleRoot, ".agents", "plugins", "marketplace.json"),
    {
      name: details.marketplaceName,
      interface: {
        displayName: `${metadata.name} Local`,
      },
      plugins: [
        {
          name: metadata.name,
          source: {
            source: "local",
            path: "./",
          },
          policy: {
            installation: "AVAILABLE",
            authentication: "ON_INSTALL",
          },
          category: "Development",
        },
      ],
    },
  );
  return details;
}
