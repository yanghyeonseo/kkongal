import { apiRequest } from "./client.js";

function normalizeInterest(item) {
  return {
    id: item.id,
    keyword: item.keyword,
    description: item.description ?? "",
    priority: item.priority ?? 3,
  };
}

export async function getMyInterests() {
  const data = await apiRequest("/api/interests/");
  return data.map(normalizeInterest);
}

export async function createInterest(keyword) {
  const data = await apiRequest("/api/interests/", {
    method: "POST",
    body: JSON.stringify({
      keyword,
    }),
  });

  return normalizeInterest(data);
}

export async function deleteInterest(id) {
  await apiRequest(`/api/interests/${id}/`, {
    method: "DELETE",
  });
}

export async function updateMyInterests(nextInterests) {
  const currentInterests = await getMyInterests();

  const nextKeywords = nextInterests
    .map((interest) => interest.keyword.trim())
    .filter(Boolean);

  const uniqueNextKeywords = [...new Set(nextKeywords)];

  const currentKeywords = currentInterests.map((interest) => interest.keyword);

  const interestsToDelete = currentInterests.filter(
    (interest) => !uniqueNextKeywords.includes(interest.keyword),
  );

  const keywordsToCreate = uniqueNextKeywords.filter(
    (keyword) => !currentKeywords.includes(keyword),
  );

  await Promise.all(
    interestsToDelete.map((interest) => deleteInterest(interest.id)),
  );

  await Promise.all(keywordsToCreate.map((keyword) => createInterest(keyword)));

  return getMyInterests();
}
