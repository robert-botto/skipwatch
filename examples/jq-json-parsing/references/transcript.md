# Transcript

[00:00] Have you ever felt completely lost inside a giant text file? Wait, let me make this
[00:04] scene even worse. What if all that text was actually unparsed JSON? You open it up,
[00:09] your screen is just a wall of brackets and quotes. You know, the answer is buried in there somewhere.
[00:13] Trying to find it is literally the definition of finding a needle in a hay stack. I remember
[00:17] this one time I was staring at a massive log file from a server. Thousands and thousands of lines
[00:22] of nested JSON. All I needed to do was to find one specific request ID we knew for a fact caused some
[00:27] issues. It was so large online JSON parsers froze trying to handle it. I spent hours scrolling and
[00:32] ripping my way through different parts of copy text. My eyes started to hurt and I felt like
[00:37] I was getting absolutely nowhere. Over the last decade, I probably wasted hundreds of hours doing
[00:42] exactly that. Here's a fun fact. According to research, your brain can only really hold
[00:46] about four pieces of information at one time. When you try to manually track nested data,
[00:52] you're forcing your brain to do something it just isn't built for. Now, most people think you have
[00:56] two bad options. either search manually and get a headache or waste time writing scripts to parse
[01:01] the file. But that's not the whole story. There's one tool that lets you speak the language of JSON
[01:07] directly from your command line. JQ. But jQ isn't just a tool or a CLI. It's a fullblown language.
[01:14] It's a combination of SED GREP and AWK but for JSON. I'm not just talking about finding a value. I'm
[01:20] talking about filtering, manipulating, and bending any JSON data to your will with a
[01:25] single command. I'm going to show you how to use JQ to make you feel like you have superpowers.
[01:34] JQ, as we already established, isn't just a command line utility. It's a very high level
[01:39] programming language handling JSON, which just for context stands for JavaScript object notation.
[01:44] But as most of you probably already know, is used by most web systems and a default way to
[01:49] send and receive data using REST APIs. JQ was first released on October 2012 by Steven Dolan
[01:55] attempting to create the famous Unix utility said but for JSON there's a Go implementation called Go
[02:00] JQ which also extends JQ to support YAML there's another way to do that and much more we'll get
[02:06] there another port obviously is written in Rust because you can't have a tool that isn't rewritten
[02:11] using the Krabland Jack goal is to be faster and more correct whatever this means last but not
[02:18] least since JQ is a programming language after all JQJQ is a JQ implementation in well yeah I should
[02:25] print that on a t-shirt. JQ is a lightweight and flexible command line JSON processor as
[02:30] they put it like said but for JSON data if you've noticed the URL is JSON lang and though their page
[02:36] doesn't mention it jq is a programming language a very much specific naroscoped highle one but
[02:42] a language nevertheless if somehow you don't already have jq installed there's binaries for
[02:47] download available for every package manager in existence and it works like this in front
[02:52] of you there's a Jason describing the best startup team I know of led by Richard Hris
[02:56] There are some startup information location and a team holds the array of team members. Now mind
[03:01] you this JSON is already pitified by Neovim and then saved into a JSON file with nice structure.
[03:07] JQ takes a reference in this case dot is entire object and the file to read or stream to input.
[03:13] We get a color-coded JSON output nice but not life-changing. And this is where the language
[03:18] kicks in. Let's get the team for example. This is an array of members. Just by asking for team,
[03:24] we get the list surrounded by arrays brackets. But jq comes with an iterator. Empty brackets
[03:29] is basically asking for all objects and there they are one after the other. But here's where
[03:34] it gets fancy. First, we can ask for a specific object as one would imagine in an array, which
[03:39] is nice. However, leaving the index clear and then asking for a name, for example, gets the iterator
[03:45] to extract only relevant names from each object in the array of team members. One notable hidden
[03:50] feature which is especially useful when scripting with jq is stripping the result from surrounding
[03:55] quotes using the rod data flag like so. Now before moving forward let's make it clear jQu takes any
[04:02] kind of input stream or files you can echo raw JSON then pipe it over to jq and you get a parsed
[04:08] structured color-coded data always. This becomes even more critical when fetching raw data with
[04:14] curl like the jq projects commits from GitHub for example. This nasty unreadable information
[04:20] can be sent to the tool and voila. As mentioned, go as deep as you like. Take the first item and
[04:25] restructure the keys with your own object like a message holding the commit message or a name
[04:30] holding the commit.com.name. Is your company's AI a tangled mess of different tools and systems?
[04:35] That's what they call AI sprawl. And it makes everything more complicated, less secure, and
[04:40] much slower. But there's a simpler way. Meet area. They've built an enterprise platform that brings
[04:44] all your AI together in one place, making it easy to manage and use. With area, teams can build AI
[04:49] agents fast. They have no code tools and pre-built templates, so anyone can create a solution,
[04:54] not just engineers. But for those who do code, area also supports custom Python development. So,
[04:59] everyone can build their agents their way. Here's the best part. Area is model agnostic. That means
[05:03] they don't force you to use one AI model. You have the freedom to pick and switch between the best
[05:07] ones for each job, saving you money and improving performance without having to rebuild anything.
[05:12] Plus, area connects directly to your company's data and systems. This makes sure your AI has
[05:16] the right information while keeping it secure. Once you've built something great, you can share
[05:20] it with the area community. Browse readymade agents and templates and jump start your next
[05:24] project with ideas from other builders. Stop the prawl. Get your AI under control with area. Visit
[05:29] area.ai to start your free trial. Now, back to the video. JQ comes with some useful flags. We've seen
[05:35] minus R for raw input, removing all surrounding notation. Hyphen C for compact compresses the
[05:40] structure back to its condensed line form. As with other languages, when addressing an array,
[05:45] you can select rangebased elements. But JQ's real power is its internal functions. A useful one
[05:50] is the length of objects, which is nice, but you haven't seen selection yet. With select,
[05:54] we can do all sorts of stuff such as picking the team members whose salary is over 115K and boom,
[06:02] Garedon is off the list. Flipping the operator does what you think it would. There's of course
[06:07] also the usual operators of equal not equal to work with when selecting and filtering. Now,
[06:12] of course, this is a simple example. Take this to the world of application logs or load balancer
[06:17] access logs. If you ever had the pleasure to search through one and you start realizing the
[06:21] power of this thing, I can't even begin to tell you how many hours I managed to burn on slicing
[06:26] and gripping longjent files as if they were raw text and banging my head with frustration. So far,
[06:31] we've just selected a few objects. What if we want to clear unnecessary data? I mean,
[06:35] seriously, think about the power of it. Check this out. I can select the team's list, but delete the
[06:40] skills to clean the result. Much better. Want to clean further? Just pipe it on and delete
[06:45] more keys. Okay, that's rather simple. When things get more complicated, especially when scripting,
[06:50] jq allows you to set arguments. For example, we can define that n is for dh. Then select a name
[06:56] from the team where it matches the parameter n. But what if you're unsure of the structure and
[07:02] need to explore it a little? Keys gets you well the keys of an object which can also be applied
[07:07] to a nested item like a list. Now remember the structuring option. Let's use the pi piper team
[07:13] to build an object. I'll use a new key called person for the name. Then a skill would be they
[07:18] can do and pick a skill but only the first one on every list. And there I have pairs for team member
[07:24] and skills. The has function will return a boolean based on the existence of a key. So start her up
[07:29] isn't part of this JSON but startup very much is if we want to select only team members who have
[07:35] the coding skill on their tool belt. We can use whatever is indexed for that. And while code isn't
[07:40] exactly there, Java is the mesh's superpower. Okay, this is child's play. Let's run a realworld
[07:46] scenario with a proper humongous JSON file like you've all once seen before. This is a stream of
[07:51] logs thankfully structured in JSON but completely unreadable. Grapping this thing for a specific
[07:57] message is quite literally looking for a needle in a hay stack. Sending them to Jake without touching
[08:02] is already miles better even if you're grapping things. However, if we dig in starting from
[08:07] noticing we're looking at an array of messages. We start with 6,52 lines. Now, yes, it's not the
[08:15] amount of messages. Still, check this out. We'll get the first object keys. Inside details, there's
[08:19] another nested object. Let's say we want all the lines with latency larger than the arbitrary 4422
[08:25] just because it's the first element on the left. Got it? Now, let's count. We're at 858. And again,
[08:31] not objects. There is a way to count the objects themselves by piping a real countable data set,
[08:36] like an array, to the length function. reading everything, typing the length gives us 500 objects
[08:42] of log lines in total. However, running it after the latency gives us a weird long list of sixes,
[08:48] which is the number of keys in each object. Not quite what we need. An easy fix is to
[08:52] wrap the result in list brackets like so. Now, the length will count the number of returned objects,
[08:58] 66 of them. Often times, especially with logs, you'd want to filter a log level. So, just like we
[09:03] plucked Jared from Pi Piper earlier, this time we use the comparison operator for warning lines or
[09:09] errors. Miles better than grappling error like I probably done thousands of times in my life.
[09:14] We've already established the fact that this is a programming language and as such it recognizes
[09:19] regular expressions, mathematical operators, and results. It can have parameters and assignments
[09:24] which we've used earlier. It even has comments and conditionals. Since you can grab all of it in the
[09:29] docs, I want to talk to you about the elephant in the room. More like three elephants to be
[09:33] honest. The first is JQ ports. As with many other utilities, JQ is popular enough to have forks
[09:38] that are also quite popular, noticeably in Go and Rust. Let's start with the first. Go JQ is a pure
[09:44] JQ implementation in Go. Installable through all popular package managers and basically used like
[09:50] jq with a few minor differences. You'll find all the usuals, but here's what caught my eye.
[09:55] JQ ers are not very friendly to say the least. Go jq aims to reconcile this with friendly
[10:00] explanations pointing exactly where the problem lies and hints heavily to help you fix the prompt.
[10:05] The other reason one may consider to opt for go jq is the standard yet missing yl support from jq
[10:11] itself. Add yl input to the flags and there we are a parsed output. You can keep quering as normal
[10:17] like there's no difference. And you've probably noticed all of this was sent back as JSON.
[10:22] So if you're also interested in the output, add the YAML output as well. And there it is. There
[10:26] are a few other differences to consider all listed in the project. But I don't use Gojq. I could,
[10:33] but I find it much easier to use the other elephant in the room, YQ, a parser for, well,
[10:38] you guessed it, a very popular project, which by the way also handles JSONs, XML, CSVs, toml,
[10:44] and others, which are all relatively new. Not quite adhering to the Unix philosophy like JQ,
[10:49] but that's beside the point. It was originally a jQ for YAML and a quick look at the usage tells
[10:54] the story. Same syntax, concepts and everyday use. So you can pick it up without thinking too much.
[10:59] It parses the data, color codes like JQ would, can iterate objects, use advanced functions like
[11:04] delions and chain further queries just like its spiritual father would. Now before moving to the
[11:09] grand finale, there are two small utilities that not enough people know, especially JQ users, and
[11:15] it's a shame they don't. JQP is a toy written in Go and essentially build jq into a dynamic UI that
[11:22] makes jq quering so much easier. It takes JSON in std in from where you can freely query an object,
[11:29] go further and further again backwards or change the query. No command line reruns. The object is
[11:34] always visible in front of you on the left pane. Simple but genius. Its sibling Brun built by a
[11:40] really cool pug bounty hunter who happens to love go by the name Tom Hudson comes in where
[11:45] you either don't have time for jQ or just need to flatten the data and it does exactly that. Throw
[11:50] JSON in and it lays flat in greable entries, hence its name grappable JSON. A poor man's jQ if you
[11:57] will. I still very much am using jq in scripts, automation servers, CI pipelines and every once in
[12:03] a while when I need a quick extraction. However, I don't use Go JQ or YQ or Gron. And some of you can
[12:09] probably guess why. So, finally, here's the last elephant in the room, Nushell. And before I'll
[12:14] show you just how big of an elephant Nushell really is, especially when talking about JQ,
[12:19] I will remind you that I have a couple of videos discussing the basics, advanced features, but
[12:23] also pros and cons, and when you should consider adopting it. It is still, despite some drawbacks,
[12:28] my local daily driver, but it's not for everyone. Here's the gist of it. When you open a JSON file
[12:33] with new shell, you literally get the keys in a table. It'll even suggest the nested objects for
[12:37] you to further query. Pipe it to the next function like get team and the output is already structured
[12:42] in a table. Need a filter? Well, the syntax can't get any easier than this. Where salary
[12:47] is adding an operator and a comparison target. It can convert to and from JSON, YAML, and any other
[12:53] format you can think of. One important caveat. While Nell is awesome, it's not a full-blown
[12:58] programming language. You can't do anything you want with it like you can with JQ and it's made to
[13:03] make your life easier when working with data. Just to prove this point, a quick rement mention to
[13:08] JQJQ. Yeah, the JQ in the power of three project. JQ is an absolute JSON superpower. But if you find
[13:14] yourself using it almost every day, I'd take a serious look at new shell on this next video. It's
[13:19] a shell for data reads JSON natively as well as other formats and puts it into a querable
[13:23] structure that makes it a breeze to read. Thank you for watching and I'll see you on the next
