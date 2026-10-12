/** Generated from player.schema.json. */

/**
 * The lecture fields that slides.json and player.json share. Open, so player.schema.json can extend it; the root schemas close it.
 */
export interface PlayerJson {
  /**
   * Schema version, incremented on incompatible changes.
   */
  version: 1;
  /**
   * The course title, from course.json.
   */
  course: string;
  /**
   * The lecture's output name, such as "lecture-01".
   */
  name: string;
  /**
   * The lecture's title.
   */
  title: string;
  /**
   * The lecture number, or null for an unnumbered lecture.
   */
  number: number | null;
  slides: (ImageSlide | MarkdownSlide | CodeSlide)[];
  /**
   * The lecture MP3, relative to player.json.
   */
  audio: string;
}
export interface ImageSlide {
  /**
   * The section number, counted across the whole course: the N in the transcript's "## [N] Title" heading and the audio chapter "[N] Title".
   */
  n: number;
  title: string;
  /**
   * The file the slide came from, relative to the course materials directory.
   */
  source: string;
  /**
   * Where in the source: "page 3", "slide 2", "section 4", "cell 5", or null for the whole file.
   */
  locator: string | null;
  /**
   * What the lecture says while this slide shows: the transcript's "## [N]" section.
   */
  narration: string;
  /**
   * Where the slide's narration starts in the audio, in milliseconds: its audio chapter's start.
   */
  start_ms: number;
  /**
   * Where the slide's narration ends in the audio, in milliseconds: its audio chapter's end.
   */
  end_ms: number;
  kind: "image";
  /**
   * image slides: the WebP image, relative to this file.
   */
  image: string;
  /**
   * image slides: the image width in pixels.
   */
  width: number;
  /**
   * image slides: the image height in pixels.
   */
  height: number;
}
export interface MarkdownSlide {
  /**
   * The section number, counted across the whole course: the N in the transcript's "## [N] Title" heading and the audio chapter "[N] Title".
   */
  n: number;
  title: string;
  /**
   * The file the slide came from, relative to the course materials directory.
   */
  source: string;
  /**
   * Where in the source: "page 3", "slide 2", "section 4", "cell 5", or null for the whole file.
   */
  locator: string | null;
  /**
   * What the lecture says while this slide shows: the transcript's "## [N]" section.
   */
  narration: string;
  /**
   * Where the slide's narration starts in the audio, in milliseconds: its audio chapter's start.
   */
  start_ms: number;
  /**
   * Where the slide's narration ends in the audio, in milliseconds: its audio chapter's end.
   */
  end_ms: number;
  kind: "markdown";
  /**
   * markdown slides: the slide's text as Markdown, with math in LaTeX ($...$ and $$...$$). May be empty.
   */
  markdown: string;
}
export interface CodeSlide {
  /**
   * The section number, counted across the whole course: the N in the transcript's "## [N] Title" heading and the audio chapter "[N] Title".
   */
  n: number;
  title: string;
  /**
   * The file the slide came from, relative to the course materials directory.
   */
  source: string;
  /**
   * Where in the source: "page 3", "slide 2", "section 4", "cell 5", or null for the whole file.
   */
  locator: string | null;
  /**
   * What the lecture says while this slide shows: the transcript's "## [N]" section.
   */
  narration: string;
  /**
   * Where the slide's narration starts in the audio, in milliseconds: its audio chapter's start.
   */
  start_ms: number;
  /**
   * Where the slide's narration ends in the audio, in milliseconds: its audio chapter's end.
   */
  end_ms: number;
  kind: "code";
  /**
   * code slides: the file's contents.
   */
  code: string;
  /**
   * code slides: a syntax highlighting language name, such as "python" or "scheme".
   */
  language: string;
}
