---
name: jq-json-parsing
description: Queries, filters, counts and reshapes JSON files and API output from the command line with jq. Use when the user wants to dig through large or nested JSON, for example "pull every name out of this JSON array with jq", "count the log entries where latency is over a threshold", "filter JSON logs by level", "select objects whose array field contains a value". Not for converting JSON to other formats, editing JSON by hand in an editor, or choosing a general data shell.
compatibility: jq (also gojq, yq and Nushell for the comparisons) as shown in the source video.
metadata:
  source_url: "https://www.youtube.com/watch?v=YrVR09v78Dc"
  source_author: "@devopstoolbox"
  source_title: "You've been parsing JSON Wrong"
  source_date: "2025-10-10"
  extracted_at: "2026-10-12"
  extracted_by: "skipwatch 0.1.0"
---

# Query, filter and reshape JSON with jq

## What this does

You end up able to pull single values, iterate arrays, filter with select, count matches and explore unknown JSON (including large log files) with one jq command each. The steps follow the video's demo on a small team file (pp.json) and a 500-entry log file (logs.json); exact commands come from the screen, and steps the creator only described aloud carry their words instead of a command.

## Prerequisites

- jq installed, or Docker to run the official image (as of 2025-10-10).
- A JSON file or a command that prints JSON (for example curl against an API).

## Procedure

1. Install jq from your package manager, or run the official Docker image against a file in the current directory.

   ```
   docker run --rm -i -v "$PWD:$PWD" -w "$PWD" ghcr.io/jqlang/jq:latest '.version' package.json
   ```

   Expected: the value of the version key from package.json is printed. [on-screen 01:10]

2. Print the whole document with the identity filter (a single dot) followed by the file name.

   > JQ takes a reference in this case dot is entire object and the file to read or stream to input.

   Expected: the full JSON, pretty-printed and color-coded. [spoken 03:07]

3. Read one top-level key.

   ```
   jq '.team' pp.json
   ```

   Expected: the value of team, here an array wrapped in brackets. [on-screen 03:28]

4. Iterate the array with empty brackets and take one field from every element.

   ```
   jq '.team[].name' pp.json
   ```

   Expected: one name per line, without the surrounding array. [on-screen 03:41]

5. Add the raw flag when scripting, so strings print without quotes.

   > feature which is especially useful when scripting with jq is stripping the result from surrounding quotes using the rod data flag like so.

   Expected: bare strings with no surrounding quotes. [spoken 03:50]

6. Pipe JSON in from another command instead of a file, for example echo, or curl against an API.

   > kind of input stream or files you can echo raw JSON then pipe it over to jq and you get a parsed

   Expected: the same parsed, color-coded output as from a file. [spoken 04:02]

7. Build your own object from selected fields, for example a message key holding a nested commit message.

   > Take the first item and restructure the keys with your own object like a message holding the commit message or a name

   Expected: a new object containing only the keys you named. [spoken 04:20]

8. Add the compact flag (the creator says "Hyphen C") to collapse output back to one line per value.

   > Hyphen C for compact compresses the structure back to its condensed line form.

   Expected: each result on a single line. [spoken 05:35]

9. Slice an array by index range.

   ```
   jq '.team[1:2]'  pp.json
   ```

   Expected: an array holding only the element at index 1 (in the video, the "Dinesh Chugtai" object). [on-screen 05:48]

10. Use the length function to measure an object or array.

    > is the length of objects, which is nice, but you haven't seen selection yet. With select,

    Expected: a number. [spoken 05:50]

11. Filter array elements with select and a numeric comparison, for example salary over a threshold; flip the operator for the opposite set.

    > we can do all sorts of stuff such as picking the team members whose salary is over 115K and boom,

    Expected: only the objects that pass the comparison. [spoken 05:54]

12. Filter on exact equality inside select.

    ```
    jq '.team[] | select(.name=="Jared Dunn")' pp.json
    ```

    Expected: only the object whose name matches. [on-screen 06:38]

13. Pipe the selection into del to remove keys you do not need, and pipe again to delete more.

    > I can select the team's list, but delete the skills to clean the result.

    Expected: the same objects without the deleted keys. [spoken 06:40]

14. Pass a value in from the shell as a named argument and compare against it inside select.

    > jq allows you to set arguments. For example, we can define that n is for dh. Then select a name

    Expected: only the elements matching the argument's value. [spoken 06:50]

15. Run keys to list an object's keys when you do not know the structure; it also works on a nested item.

    > Keys gets you well the keys of an object which can also be applied

    Expected: an array of key names. [spoken 07:02]

16. Iterate the array and build a new object per element with your own key names, for example person for the name and the first item of each skills list.

    > I'll use a new key called person for the name.

    Expected: one small object per element with only your keys. [spoken 07:13]

17. Use the has function to test whether a key exists.

    > The has function will return a boolean based on the existence of a key.

    Expected: true or false. [spoken 07:24]

18. Select elements whose array field contains a value by piping the field into index.

    ```
    jq '.team[] | select(.skills | index("Java"))' pp.json
    ```

    Expected: only members whose skills list contains "Java" (in the video, Dinesh Chugtai). [on-screen 07:40]

19. On a large unknown file, print the first element.

    ```
    jq '.[0]' logs.json
    ```

    Expected: one log object, with nested objects such as details visible. [on-screen 08:20]

20. List that first element's keys before writing a filter.

    ```
    jq '.[0] | keys' logs.json
    ```

    Expected: an array of the entry's key names. [on-screen 08:20]

21. Count matching objects by wrapping the filter in brackets before length.

    ```
    jq '[.[] | select(.details.latency_ms > 4422)] | length' logs.json
    ```

    Expected: a single count (66 in the video), not a list of per-object numbers. [on-screen 08:54]

22. Filter log lines by level with the same equality comparison used in step 12, applied to each entry's level field (step 19 shows an entry whose level is WARNING).

    > this time we use the comparison operator for warning lines or

    Expected: only entries whose level is the one you chose. [spoken 09:03]

## Decision points

- **jq or gojq:** gojq is a Go port used like jq; the creator points to its friendlier error messages and YAML input and output. The same bad query in each:

  ```
  echo '[1,2,3]' | jq '.foo & .bar'
  echo '[1,2,3]' | gojq '.foo & .bar'
  ```

  jq prints `jq: error: syntax error, unexpected INVALID_CHARACTER, expecting end of file at <top-level>, line 1, column 6:`; gojq prints `gojq: invalid query: .foo & .bar` with a caret under `unexpected token "&"`. [on-screen 09:59]
- **YAML input:** yq uses the same syntax and concepts as jq. [on-screen 11:08]

  ```
  yq '.team[] | del(.skills)| del(.salary)' pp.yaml
  ```

- **Interactive exploration:** jqp builds jq into an interactive UI over stdin; gron flattens JSON into greppable lines when you do not need jq. [spoken 11:15]
- **Daily local use:** the creator keeps jq for scripts, automation servers and CI pipelines, and uses Nushell locally, where `open pp.json | get team` shows the data as a table. Nushell is not a full programming language like jq. [on-screen 12:39]

## Gotchas

- Running length directly after a filter that returns many objects prints one number per object (the key count of each), not a total. Wrap the filter in brackets first, as in step 21. [spoken 08:42]
- The creator says huge JSON files froze online JSON parsers; jq on the command line handled them. [spoken 00:27]
- The creator calls the raw flag "minus R for raw input" at 05:29; the flag itself is not visible in the sampled frames, so check `jq --help` for the raw output option before scripting with it. [spoken 05:29]
- Step 12's command was read from a frame where shell autosuggestion text was shown in grey (reader confidence 0.6); the typed part may differ.
- jq's own error messages are terse; see the gojq comparison under Decision points.

## Verification

Run step 3 and step 4 on your file: step 3 should print the array with brackets and step 4 one value per line. For counts, the bracketed form in step 21 must print a single number.

## Worked example

With a file `<your-file>.json` holding a `team` array of objects that each have `name`, `role`, `skills` and `salary`:

```
jq '.team' <your-file>.json
jq '.team[].name' <your-file>.json
jq '.team[1:2]' <your-file>.json
jq '.team[] | select(.skills | index("<skill>"))' <your-file>.json
```

With a log file `<your-logs>.json` holding an array of entries with a nested `details.latency_ms`:

```
jq '.[0] | keys' <your-logs>.json
jq '[.[] | select(.details.latency_ms > <threshold>)] | length' <your-logs>.json
```

## Unverified and gaps

Steps 2, 5, 6, 7, 8, 10, 11, 13, 14, 15, 16, 17 and 22 come from the narration only: the sampled frames did not catch their exact commands, so each carries the creator's words instead of a command. Write those filters from the jq manual (jqlang.org, shown at 01:10).

## Attribution

Distilled from You've been parsing JSON Wrong by @devopstoolbox (https://www.youtube.com/watch?v=YrVR09v78Dc), posted 2025-10-10, with SkipWatch. The workflow and wording are the creator's.
