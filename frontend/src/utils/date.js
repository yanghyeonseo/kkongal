export function formatRelativeTime(dateString) {
  if (!dateString) {
    return "";
  }

  const targetDate = new Date(dateString);
  const now = new Date();

  const diffMs = now - targetDate;
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) {
    return "방금 전";
  }

  if (diffMinutes < 60) {
    return `${diffMinutes}분 전`;
  }

  if (diffHours < 24) {
    return `${diffHours}시간 전`;
  }

  if (diffDays === 1) {
    return "어제";
  }

  if (diffDays < 7) {
    return `${diffDays}일 전`;
  }

  const year = targetDate.getFullYear();
  const month = targetDate.getMonth() + 1;
  const date = targetDate.getDate();

  return `${year}.${month}.${date}`;
}

export function isToday(dateString) {
  if (!dateString) {
    return false;
  }

  const targetDate = new Date(dateString);
  const today = new Date();

  return (
    targetDate.getFullYear() === today.getFullYear() &&
    targetDate.getMonth() === today.getMonth() &&
    targetDate.getDate() === today.getDate()
  );
}
// 절대 날짜 표기(YYYY.M.D). 잘못된 값이면 빈 문자열.
export function formatDate(dateString) {
  if (!dateString) return "";

  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return "";

  return `${date.getFullYear()}.${date.getMonth() + 1}.${date.getDate()}`;
}

export function calculateDday(deadlineAt) {
  if (!deadlineAt) {
    return null;
  }

  const today = new Date();
  const deadline = new Date(deadlineAt);

  today.setHours(0, 0, 0, 0);
  deadline.setHours(0, 0, 0, 0);

  const diffMs = deadline - today;
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

  return diffDays;
}
