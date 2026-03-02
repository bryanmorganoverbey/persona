# Virtual tours or contact landlords

I'll start by reviewing the relevant files to understand what's already been done and identify the shortlisted properties before contacting landlords.
[TOOL_CALL]
{tool => "read_file", args => {
  --file_path "/home/user/repos/vision-board/goals/2026-nomad-start/housing/minimum-requirements.md"
}}
[/TOOL_CALL]
[TOOL_CALL]
{tool => "read_file", args => {
  --file_path "/home/user/repos/vision-board/goals/2026-nomad-start/housing/deal-breakers.md"
}}
[/TOOL_CALL]
[TOOL_CALL]
{tool => "read_file", args => {
  --file_path "/home/user/repos/vision-board/goals/2026-nomad-start/pets/remi.md"
}}
[/TOOL_CALL]
[TOOL_CALL]
{tool => "glob", args => {
  --pattern "goals/2026-nomad-start/housing/**/*.md"
}}
[/TOOL_CALL]
