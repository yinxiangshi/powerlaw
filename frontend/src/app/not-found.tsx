import Link from "next/link";
import { SearchX } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-6">
      <div className="max-w-md text-center">
        <span className="mx-auto flex size-12 items-center justify-center rounded-md bg-secondary text-primary">
          <SearchX className="size-6" aria-hidden="true" />
        </span>
        <h1 className="mt-5 text-2xl font-semibold">Project not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The requested project is not available in the current workspace.
        </p>
        <Link href="/" className={buttonVariants({ className: "mt-5" })}>
          Back to projects
        </Link>
      </div>
    </main>
  );
}
