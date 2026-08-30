<script lang="ts">
import LanguageSwitcher from "@/components/LanguageSwitcher.svelte";
import OrganiserDoor from "@/components/OrganiserDoor.svelte";
import TileGrid, { type Tile } from "@/components/TileGrid.svelte";
import PublicIdentity from "@/public_shared/PublicIdentity.svelte";
import { locale, t } from "@/i18n.svelte";
import { brand, tagline } from "@/lib/branding";

/**
 * The root's signed-out face: a door with six handles.
 *
 * An organisation's front page lists its chapters, because a visitor
 * there is looking for one of them. Nobody arrives at the bare root
 * looking for an organisation. They arrive wanting to make one thing,
 * so the six things this tool makes are the page, and each tile opens
 * that thing's create form rather than a description of it.
 */
const b = brand();

/* Ordered the way somebody organising something meets them: settle a
 * date, put the event up, share out the work, then ask people
 * something, and last the one that is for the evening itself.
 *
 * Six tiles in two columns is three full rows, and the grid is two
 * columns at every width (docs/design-quizzes.md part 4,
 * docs/design-kompas.md part 0). */
const tiles = $derived<Tile[]>([
  { key: "events", to: "/event/new", label: t("home.eventsTile"), hint: t("home.eventsHint") },
  { key: "datepolls", to: "/datepoll/new", label: t("home.datepollsTile"), hint: t("home.datepollsHint") },
  { key: "chores", to: "/chore/new", label: t("home.choresTile"), hint: t("home.choresHint") },
  { key: "forms", to: "/form/new", label: t("home.formsTile"), hint: t("home.formsHint") },
  { key: "quizzes", to: "/quiz/new", label: t("home.quizzesTile"), hint: t("home.quizzesHint") },
  { key: "compasses", to: "/compass/new", label: t("home.compassesTile"), hint: t("home.compassesHint") },
]);
</script>

<!-- The same column and header as an organisation's front page: the
     root is not a different site, it is the same app without an
     organisation in front of it. -->
<main class="container-wide stack">
  <header class="public-header">
    <PublicIdentity title={b.wordmark} subtitle={tagline(locale())} />
    <LanguageSwitcher />
  </header>
  <TileGrid {tiles} />

  <OrganiserDoor />
</main>
