import { get, post } from "@/api/client";
import { apiQuery } from "@/api/queries.svelte";
import { createEntityCrud } from "@/composables/createEntityCrud.svelte";
import { mutation } from "@/composables/mutation.svelte";
import { route } from "@/router/navigation.svelte";
import type {
  FormCreate,
  FormListOut,
  FormOut,
  FormQuestionIn,
  FormQuestionOut,
  FormSubmit,
  FormSubmitAck,
  FormSubmission,
  FormSummary,
  FormUpdate,
  PublicFormOut,
} from "@/api/types";

/**
 * The forms table's three products.
 *
 * A questionnaire, a quiz and a kompas differ by what an answer means
 * (nothing, a key, a pole) and by how the questions are walked through
 * (``docs/design-quizzes.md``, ``docs/design-kompas.md``), and by
 * nothing at all at this layer: the same CRUD, the same summary, the
 * same by-slug read, against ``/api/v1/form``, ``/api/v1/quiz`` or
 * ``/api/v1/compass``. So the surface is built once and handed out one
 * per product, and an organiser page asks ``formsApi()`` which one it is
 * on rather than importing one by name.
 */
export type {
  FormCreate,
  FormListOut,
  FormOut,
  FormQuestionIn,
  FormQuestionOut,
  FormSubmit,
  FormSubmitAck,
  FormSubmission,
  FormSummary,
  FormUpdate,
  PublicFormOut,
};

/** The products, and the API prefix each one lives under. */
export type FormResource = "form" | "quiz" | "compass";

/** Every resource, so a caller that has to cover all of them (the copy
 *  test, a route table) enumerates rather than remembers. */
export const FORM_RESOURCES: readonly FormResource[] = ["form", "quiz", "compass"];

function makeApi(resource: FormResource) {
  // The chapter-scoped CRUD surface comes from the shared factory; only
  // the form-specific reads and the public submit are here.
  const crud = createEntityCrud<FormListOut, FormOut, FormCreate, FormUpdate>({ resource });
  const base = `/api/v1/${resource}`;

  return {
    resource,
    ...crud,

    summary(formId: () => string) {
      return apiQuery<FormSummary>(
        () => [resource, formId(), "summary"],
        () => `${base}/${formId()}/summary`,
      );
    },

    /** Per-submission rows, the CSV's source. Not a query: it is a
     *  one-shot download, so it is a thin fetch helper. */
    fetchSubmissions(formId: string) {
      return get<FormSubmission[]>(`${base}/${formId}/submissions`);
    },

    /** Public fetch by slug. Needs no auth. */
    publicBySlug(slug: () => string, enabled?: () => boolean) {
      return apiQuery<PublicFormOut>(
        () => [resource, "by-slug", slug()],
        () => `${base}/by-slug/${encodeURIComponent(slug())}`,
        { enabled },
      );
    },

    submit: () =>
      mutation((vars: { slug: string; payload: FormSubmit }) =>
        post<FormSubmitAck>(`${base}/by-slug/${encodeURIComponent(vars.slug)}/submit`, vars.payload),
      ),
  };
}

export const forms = makeApi("form");
export const quizzes = makeApi("quiz");
export const compasses = makeApi("compass");

const BY_RESOURCE: Record<FormResource, ReturnType<typeof makeApi>> = {
  form: forms,
  quiz: quizzes,
  compass: compasses,
};

/** Which product the page is on. The route says so (``meta.resource``);
 *  the four pages are registered once per product, because everything
 *  they render is the same. An absent or unknown value is the
 *  questionnaire, which is the base vocabulary. */
export function formsApi() {
  const resource = route.meta.resource;
  return (resource && BY_RESOURCE[resource]) || forms;
}
