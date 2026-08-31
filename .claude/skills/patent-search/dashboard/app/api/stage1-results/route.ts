import { NextResponse } from "next/server";
import { readdir } from "fs/promises";
import { join } from "path";

export const runtime = "nodejs";

export async function GET() {
  const dir = join(process.cwd(), "public", "stage1-results");
  try {
    const files = await readdir(dir);
    const jsonFiles = files
      .filter((f) => f.endsWith(".json"))
      .sort()
      .reverse(); // 최신순
    return NextResponse.json({ files: jsonFiles });
  } catch {
    return NextResponse.json({ files: [] });
  }
}
