Priority:
1. If vulnerability is found, the UI should show a button to reject the PR. At the moment, only 'Approve and post' button is showed. Think about a solution.
2. Check "Review summary" issue. Markdown format is not rendered.
3. Check vulnerabilities in the code of the app itself

Low priority:
1. Fix start.bat so that it doesn't block on "activating venv and installing dependencies..." when the dependencies are already installed and remove bad chars from the output
2. Add more test repos
3. Check github integration to effectively approve and reject PRs
4. Renew frontend with a better UI/UX
5. Extend the app with more features

Done:
1. Check response format issues in the log of the backend. This must be the reason why security issues are not reported in the frontend. If the problem is fixed for security agent, adopt the same solution for the others