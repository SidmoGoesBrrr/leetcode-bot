# graphql_queries.py

LEETCODE_STATS_QUERY = """
query LeetCodeStats($username: String!, $year: Int!, $recentN: Int!) {
  matchedUser(username: $username) {
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
      }
    }
    problemsSolvedBeatsStats {
      difficulty
      percentage
    }
    userCalendar(year: $year) {
      streak
      submissionCalendar
    }
  }
  recentAcSubmissionList(username: $username, limit: $recentN) {
    id
    title
    titleSlug
    timestamp
  }
}
"""


QUERY_IF_USER_EXISTS = """
        query userPublicProfile($username: String!) {
        matchedUser(username: $username) {
            username
        }
        }
        """

QUERY_USER_SOLVED = "query getACSubmissions ($username: String!, $limit: Int) { recentAcSubmissionList(username: $username, limit: $limit) { titleSlug timestamp } }"
QUERY_SINGLE_PROBLEM = "query questionTitle($titleSlug: String!) { question(titleSlug: $titleSlug) { isPaidOnly } }"
QUERY_DUEL_PROBLEM = """
        query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
          problemsetQuestionList: questionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) {
            questions: data { title titleSlug difficulty }
          }
        }"""


UPCOMING_CONTESTS_QUERY = """
query upcomingContests {
  upcomingContests {
    title
    titleSlug
    startTime
    duration
    __typename
  }
}
"""
