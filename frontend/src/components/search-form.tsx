import { searchPlayer } from "@/app/actions";
import {
  PLATFORM_LABELS,
  PLATFORM_SLUGS,
  type PlatformSlug,
} from "@/lib/platform";

type SearchFormProps = {
  defaultPlatform?: PlatformSlug;
  defaultName?: string;
};

export function SearchForm({
  defaultPlatform = "pc",
  defaultName = "",
}: SearchFormProps) {
  return (
    <form action={searchPlayer} className="flex flex-col gap-3 sm:flex-row">
      <label className="sr-only" htmlFor="platform">
        Platform
      </label>
      <select
        id="platform"
        name="platform"
        defaultValue={defaultPlatform}
        className="h-11 rounded-lg border border-zinc-300 bg-transparent px-3 dark:border-zinc-700"
      >
        {PLATFORM_SLUGS.map((slug) => (
          <option key={slug} value={slug}>
            {PLATFORM_LABELS[slug]}
          </option>
        ))}
      </select>
      <label className="sr-only" htmlFor="name">
        Player name
      </label>
      <input
        id="name"
        name="name"
        type="text"
        required
        maxLength={64}
        defaultValue={defaultName}
        placeholder="Player name (EA ID on PC)"
        autoComplete="off"
        spellCheck={false}
        className="h-11 min-w-0 flex-1 rounded-lg border border-zinc-300 bg-transparent px-3 dark:border-zinc-700"
      />
      <button
        type="submit"
        className="h-11 rounded-lg bg-foreground px-5 font-medium text-background"
      >
        Search
      </button>
    </form>
  );
}
