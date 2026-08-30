<script lang="ts">
import EntityListPage from "@/components/EntityListPage.svelte";
import { entityList } from "@/composables/useEntityList.svelte";
import { type FormListOut, formsApi } from "@/composables/useForms.svelte";
import { formText } from "@/composables/useFormText.svelte";
import { shareClipboard } from "@/composables/useShareClipboard.svelte";
import { get } from "@/api/client";
import { formQrUrl, publicFormUrl } from "@/lib/form-urls";
import { queryClient } from "@/lib/query-client";
import { auth } from "@/stores/auth.svelte";

/** One page, three products; the route says which. Every key resolves
 *  against the product first and falls back to the questionnaire's
 *  word, so a quiz says "quiz" wherever it has a word of its own. */
const api = formsApi();
const { L } = formText();
const copy = (key: string, params?: Record<string, unknown>) => L(`list.${key}`, params);
const archive = api.archive();
const list = entityList<FormListOut>({ archive: archive.run, copy });
const query = api.list({
  enabled: () => auth.isApproved,
  chapterId: () => list.chapter.value,
  page: () => list.chapter.page,
  search: () => list.chapter.search,
});
const share = shareClipboard({
  publicUrlFor: (slug) => publicFormUrl(api.resource, slug),
  qrUrlFor: (slug) => formQrUrl(api.resource, slug),
  copyPrefix: "form.share",
});

// Newest first is the statement's order, and the list arrives one page
// at a time.
const page = $derived(query.data ?? null);
</script>

<EntityListPage
  {copy}
  {list}
  items={page?.items ?? []}
  total={page?.total ?? 0}
  perPage={page?.per_page ?? 0}
  loaded={!auth.isApproved || !query.isPending}
  isError={query.isError}
  newPath={`/${api.resource}/new`}
  newLabel={copy("newForm")}
  detailsPath={(f) => `/${api.resource}/${f.id}/details`}
  publicUrl={(f) => publicFormUrl(api.resource, f.slug)}
  qrSrc={(f) => formQrUrl(api.resource, f.slug)}
  sharePrefix="form.share"
  copyLink={(f) => void share.copyLink(f.slug)}
  copyQr={(f) => void share.copyQr(f.slug)}
  prefetch={(id) => {
    void queryClient.prefetchQuery({
      queryKey: [api.resource, "single", id],
      queryFn: () => get(`/api/v1/${api.resource}/${id}`),
    });
    void queryClient.prefetchQuery({
      queryKey: [api.resource, id, "summary"],
      queryFn: () => get(`/api/v1/${api.resource}/${id}/summary`),
    });
  }}
>
  {#snippet count(f: FormListOut)}
    {copy("submissionCount", { n: f.submission_count })}
  {/snippet}
</EntityListPage>
