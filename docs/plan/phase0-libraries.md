# Phase 0: library work in CSTL and STL

Part of the [LectureCast plan](../../PLAN.md). This work happens in the library repos
(`~/Projects/SlidesToLectures` and `~/Projects/CourseSiteToLectures`) before any LectureCast code
is written.

The web worker calls the libraries as Python APIs, not through the CLI. Each pipeline stage (see
[pipeline.md](pipeline.md)) maps to one library call for one lecture.

1. **Progress and usage reporting.** Add an optional `reporter` (a small protocol with `step()`,
   `log()` and `usage()`) to:
   - STL: `lecture.run` and `tts.run`, replacing `print`/`Progress` in
     `slidestolectures/tts.py` and `lecture.py`.
   - CSTL: `materials.run`, `vision.run` and `WebsiteProvider.fetch`, replacing the roughly 16
     `print` calls.
   The default reporter prints, so the CLI doesn't change. Usage records Claude input and output
   tokens per call and Speechify characters, which billing needs.
2. **Chapter times.** STL `tts.encode` already computes `chapters`. Also write
   `<audio dir>/<name>.chapters.json` (`[{n, title, start_ms, end_ms}]`) so nothing has to read
   them back from the MP3.
3. **A new CSTL step, `slides`**, in `coursesitetolectures/slides.py` with a CLI command, split
   into two functions so the pipeline can run them as separate stages:
   - `slides.render(lecture)` writes slide images from the materials alone, so it can run in
     parallel with transcripts and TTS;
   - `slides.assemble(lecture)` writes `slides/<name>/player.json`. It joins each section's
     source and locator, from `course.json` (`materials.index`); its narration, from `## [N]`
     sections of the lecture transcript (the same split as STL `tts.SECTION`); and its audio
     start and end, from `chapters.json`.
   The CLI command runs both. Each slide is one of these kinds:
   - `image`: a PDF page or scanned page rendered to WebP with pymupdf. PPTX is converted to PDF
     with LibreOffice when it's installed, else it falls back to markdown.
   - `markdown`: rebuilt Google Slides, HTML, Markdown, notebook cells, and transcribed text.
   - `code`: example code files.
4. **Per-lecture calls.** Every stage after fetch must be callable for one lecture:
   `materials.run(cfg, names=[...])`, `lecture.run` and `tts.run` with one file, and the two
   `slides` functions. Check that each reads and writes only that lecture's files plus shared
   read-only inputs (`course.json`), so parallel lecture branches don't collide.
5. **Cost estimates.** `estimate(stage, workspace, lectures)` gives expected Claude tokens and
   Speechify characters before a run, for the selected lectures only. It should be calibrated
   from the two test courses, where transcripts ran about 4,000 words, or 24,000–27,000
   characters, per lecture.
6. **Injectable URL validator.** CSTL's `Web` client accepts a URL validator, so the worker can
   enforce its SSRF checks (see [pipeline.md](pipeline.md#safety-checks)).
7. **Publish both packages to PyPI.** STL first, then CSTL without its git `[tool.uv.sources]`
   entry. LectureCast pins exact versions.

## Verification

- pytest for the reporters, `chapters.json`, `render`/`assemble` and `player.json` (against a
  fixture course), per-lecture calls, the URL validator hook and estimates.
- Re-run the two test courses through the CLI and check that `player.json` slide times line up
  with the MP3 chapters.
