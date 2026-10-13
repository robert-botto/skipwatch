# Transcript

[00:00] Yesterday
[00:00] a completely new kind of AI model was
[00:03] released that's 20 to 200 times faster
[00:06] and 40 to 400 times cheaper than other
[00:09] frontier AI models. It's called JEV
[00:12] and it's actually a completely different kind of
[00:14] model that's trained in a different way from an LLM
[00:17] which of course is the type of language
[00:19] model we use with ChatGPT or Claude
[00:21] So in this video
[00:22] I want to explain to you exactly what JEV is
[00:25] how to start using it
[00:26] and I will be building three example projects
[00:29] to show you exactly what this model unlocks
[00:31] and how powerful it is
[00:32] So let's dive in. All right
[00:33] so this is probably the best graphic I've
[00:35] found that explains what JEV is
[00:37] So if you think about how currently LLMs work
[00:40] if you have your app that is asking question
[00:44] which is, is this invoice fraud?
[00:46] And then
[00:47] the LLM in this case would be
[00:50] basically answering in text form
[00:52] right? So it would say
[00:53] based on the line items and the vendor history
[00:56] which was passed here inside of the context
[00:58] this invoice appears To be legitimate
[01:01] right? So
[01:02] this could be an answer by an LLM
[01:04] And the thing here is it
[01:06] the LLM basically writes a sentence one token at a time
[01:10] and you can see in this example how
[01:12] much time this took
[01:13] 8.5 seconds. So it took a lot of
[01:15] time to evaluate this question
[01:16] Okay
[01:16] now how does this look like when Jeff
[01:19] answers the question? So same question here
[01:21] is this invoice fraud?
[01:22] The difference here is that the answer
[01:25] is actually a classification. So you can see here
[01:28] there's this category, which is fraud
[01:31] This is the, the first option, basically
[01:33] There's clean, and then there's review
[01:36] which are different ways to classify this invoice
[01:38] right? And then
[01:39] you can see that it gives you a
[01:41] probability here that this invoice is clean
[01:44] and the probability here in this example is
[01:47] 88%. So it's very likely that this invoice
[01:50] was clean. And the main difference here
[01:53] as you can see
[01:54] is it does not write text
[01:56] The output is not text
[01:58] It basically points at
[01:59] one of Your options that you will have to predefine
[02:02] but it does this in a much faster
[02:05] way. So the way to think about it
[02:06] is that LLMs generate answers
[02:09] while Jeff actually gives you probabilities
[02:12] which helps you make decisions
[02:14] So, okay, you might be asking
[02:15] okay, so what? Like, what does this really enable then?
[02:18] Well, the thing is, if you think about it
[02:20] software is actually full of these little decisions
[02:22] which are also known as if statements
[02:25] And, ultimately, if you think about the software
[02:28] it's basically just a series of if this
[02:31] then that happens, and if, you know, this new thing happens
[02:36] then you should, like, route it here, and, you know
[02:40] if this other new thing happens
[02:42] then you should, you know, escalate it to a human
[02:46] for example, right? This is basically how software works
[02:49] Okay
[02:49] so let's give you a couple of examples
[02:51] of what this can look like
[02:52] and we'll be building more examples later in
[02:54] this video as well. So in this example you see here
[02:56] this is a game
[02:57] basically, right? The input is the environment of The game
[03:00] and this character has a couple of options
[03:03] It can move left
[03:04] it can move right
[03:05] it can move forward
[03:06] it can shoot. So these are the actions
[03:08] that it can do
[03:09] and Jeff is able to
[03:10] control these actions based on these inputs in
[03:13] a super fast way. And so
[03:15] it's able to control this character in this game
[03:18] which an LLM would just not be
[03:21] able to do because it's not fast enough
[03:23] So to summarize, Jeff can pick an action
[03:27] classify, score, and rank, route
[03:30] and all of that. It can do it
[03:32] at 100x the speed
[03:33] but it cannot write a sentence
[03:35] it cannot explain itself
[03:37] it cannot write code
[03:38] and it cannot reason step by step
[03:39] And so it's basically giving up writing
[03:42] in order to get the speed
[03:43] which is the whole trade
[03:45] So the way you can think about it
[03:46] is that you can use Jeff in combination with a GBT
[03:51] and Jeff would decide what needs to happen
[03:54] and the
[03:55] LLM can then reason or generate when deeper
[03:58] intelligence is needed
[03:59] And
[03:59] that Actually opens up
[04:00] a pretty interesting category of software
[04:03] So
[04:03] let me give you a sneak peek now
[04:05] with a couple of examples
[04:06] All right
[04:06] the first thing we'll need to do
[04:07] before we can start building is go get
[04:09] an API key. So
[04:11] go to typesafe.ai, their website here
[04:14] and then if you scroll down
[04:15] you'll see here, join waitlist
[04:16] So right now, there's still a waitlist
[04:18] and they're letting some people in
[04:20] I'm lucky enough to
[04:21] to have gotten in early
[04:23] and
[04:23] I'm assuming they will let more people in
[04:25] over the next few days
[04:26] But for now, yeah, just join the waitlist
[04:28] And then once you have access
[04:30] you
[04:30] will be able to log into the console
[04:32] here. And it's quite cool
[04:33] they have like this little playground where you
[04:35] can kind of go in and
[04:37] try out a couple of things here just to understand better
[04:40] like what this model is and what it does
[04:42] And, you know
[04:43] feel free to go play around with that
[04:45] we won't do that now
[04:46] All we'd really need is an API key
[04:49] so just go here to the API keys tab
[04:51] and then you can create a new key
[04:52] here
[04:53] And then just go ahead and save your
[04:54] key somewhere in a local file
[04:57] so in your local.env file
[04:59] And then what I did Here is
[05:00] I opened up Cursor
[05:01] which is the application I use to code
[05:03] and I created a new folder here
[05:06] I just called it Jeff
[05:07] and the first prompt was this
[05:10] So I just said
[05:10] read the documentation completely and save a compressed version
[05:14] So yeah
[05:14] I want to get the documentation of Jeff
[05:17] fully compressed into my project
[05:20] just so that it's able to
[05:21] like know everything about the project
[05:24] and it can, you know, do things for me
[05:26] and
[05:26] and so that it doesn't need to
[05:27] like reference the documentation all the time and
[05:30] and go back into the browser to
[05:32] to look at stuff. So yeah
[05:33] I said, read the documentation, compress it, save it locally
[05:37] because we will be working with this model
[05:40] inside of this project
[05:41] and I want you to know everything about
[05:42] it so that we can work with it
[05:44] efficiently with the API
[05:45] And then you would also want to tell
[05:47] it where your API key is saved
[05:49] just so it knows
[05:50] and
[05:51] so it knows where the key is and
[05:52] can access it. Okay
[05:53] and once you have that
[05:54] you're ready to build something that can then
[05:56] utilize Jeff in the app that you're building
[05:59] Okay, for the first example
[06:00] I want to build a voice-controlled web browser
[06:03] So let's write the prompt here
[06:04] I want you to build an app
[06:08] using the Jeff API. It should be a web app
[06:16] where
[06:16] I can record or I can speak into
[06:20] It automatically
[06:22] transcribes
[06:24] what I say and controls the
[06:27] web browser for me. So I can say
[06:31] for example, open this website, click on this link
[06:36] et cetera
[06:37] and the browser just does
[06:39] all of that in real time
[06:42] Okay? Okay, this is done
[06:43] So let's check it out
[06:44] The dashboard control page is here
[06:46] we can, let's put it to the side
[06:49] and then it also opened up this browser window here
[06:52] which we will put here
[06:53] And I guess now we can start
[06:55] trying this out. So I can click here
[06:57] start Mike, and then it should be recording my voice
[07:00] Okay, go to wikipedia dot org
[07:03] Okay, it's working
[07:05] Okay, click on the first link
[07:14] Okay, click on the, a ferry sinks link
[07:29] Nice
[07:30] Scroll down the page a little bit
[07:39] Scroll down a bit more
[07:49] Click on the Matsuyama-Kokura ferry link
[08:03] Okay, awesome. Opens the page in Japanese now
[08:05] Okay, go back in the browser
[08:14] Nice, it went back. Amazing
[08:16] Okay, I'm going to stop the mic here
[08:17] but you can see kind of from this control panel
[08:20] a little bit what's happening
[08:21] So basically my
[08:23] my voice is being transcribed here in real time
[08:25] and then it's kind of like recording these commands
[08:28] So, okay, click on the very syncs linked
[08:31] and then, you know
[08:32] I'm guessing the
[08:33] LLM is doing some of the work here as well
[08:35] but then, Jeff is likely like
[08:38] you know
[08:39] taking all of the possibilities on that page
[08:41] and kind of giving
[08:43] the LLM a ranking of
[08:45] which link I meant or which action I
[08:47] meant. And because it's able to do it so fast
[08:50] it's able to do this basically in real
[08:52] time. So let's actually go here and
[08:55] I'm guessing the AI will be able to
[08:56] explain it better than me
[08:57] Can you explain in very simple terms
[09:00] how this actually works? Okay
[09:02] so here we go. So think of it in
[09:04] in three parts that passes a note down
[09:06] the line many times a second
[09:08] So
[09:08] your voice becomes text while you're still Talking
[09:11] The dashboard page in Chrome listens to your
[09:13] microphone in terms of speech and text
[09:15] Okay
[09:16] that makes sense. And then the next step
[09:18] is Jeff answers a quiz about that text
[09:20] okay? each time a new fragment arrives
[09:23] the Node server looks at the controlled browser window
[09:26] so it looks at what's in the browser
[09:28] makes a short list of what's on the page
[09:31] okay? Like, up to a hundred things like
[09:33] there's a link which says new
[09:35] there's a button which says search
[09:37] search, and it sends that list plus your words to Jeff
[09:40] okay? With a fixed set of multiple choice
[09:42] and yes and no questions
[09:44] like, what does the user want?
[09:46] Like, do I want to navigate?
[09:48] Do I want to search
[09:49] click, type, and so on?
[09:51] Which element on the page do they mean?
[09:53] Which website are they talking about?
[09:55] Is the sentence finished yet?
[09:57] is the user even talking to the browser
[09:59] or to someone in the room?
[10:01] Okay, interesting. and what does action buy
[10:03] delete, or send something? Okay
[10:05] cool. And after that
[10:06] then plain code decides and acts
[10:08] So the server has a handful of if
[10:10] Statements with thresholds. If is this is a command
[10:14] is below 0.5, ignore it
[10:16] so these are the
[10:17] the probability that are basically returned
[10:19] If it's under 0.5
[10:21] ignore it. And if is the sentence finished
[10:23] is below 0.6, wait for more words
[10:25] and so on. Okay
[10:26] so it has like a bunch of rules
[10:28] and based on the probabilities that it
[10:30] it's, it's getting back
[10:32] it's making those decisions and
[10:34] like acting on it basically
[10:35] And all of that
[10:37] is happening in real time
[10:38] And so the thing here is that if
[10:40] an LLM were to make this
[10:42] decision
[10:43] it would take a lot longer to
[10:45] actually arrive at that decision
[10:46] right? Because it needs to reason through the
[10:48] steps. It would need to like look at
[10:49] everything that's there and then kind of reason
[10:51] through it. Whereas Jev is just
[10:54] it gets all of that data
[10:55] and then it can make very
[10:56] fast decisions on what probability
[10:59] is it that this button should be clicked
[11:01] and then it just goes and
[11:03] and clicks that button. Okay
[11:04] so this was pretty cool
[11:05] to be honest. And actually
[11:06] when I was trying this out earlier
[11:07] it was even faster
[11:09] And I think it just came down to
[11:10] my Internet. My internet right now is a
[11:12] bit slower than before. Like earlier
[11:13] it was really just instant
[11:15] Like I said something and it just went
[11:17] instant. And in the end
[11:19] when I said
[11:20] you can actually check this out on the
[11:21] recording I did on my Twitter
[11:23] when I said go back
[11:24] it went back before I even finished my sentence
[11:27] which was actually, which was pretty crazy
[11:29] So, you know
[11:30] you can see how fast it actually is
[11:32] All right, let's do another example
[11:33] So I'm going to paste this
[11:35] prompt here and then
[11:36] explain what I want to do
[11:37] So
[11:37] I want to build
[11:38] an improved Claudia memory system
[11:40] And I'll explain what that is
[11:42] but basically I say
[11:43] look into my memory system in the Claudia
[11:45] folder. So Claudia is like my personal OS
[11:47] It's basically like a
[11:48] a folder where I have all of my
[11:50] things stored and where I start all of
[11:53] my AI chats from
[11:54] and it has a bunch of memory
[11:56] about me
[11:57] and about the things that I've done
[11:59] So
[11:59] I want it to come up with ways
[12:01] to improve my memory system using Jeff
[12:04] build improvements and build a dashboard to be
[12:06] able to demo exactly what improved and see
[12:09] the improvements. Okay. So
[12:11] just to give a bit more context
[12:13] my, the way my Claudia OS works is
[12:17] you know
[12:17] it's essentially a folder which has a couple of subfolders
[12:21] and one of those subfolders is this memory folder
[12:24] which has a bunch of daily memory files
[12:26] where whenever I chat with my AI
[12:29] from inside of this folder
[12:31] it kind of saves what I've been chatting about
[12:33] and so this kind of builds this
[12:34] like, knowledge base. And all of these other folders here are
[12:38] are things that I've built over time
[12:40] so it contains a lot of memory
[12:41] Now
[12:42] the problem with that is if
[12:43] I go
[12:44] here and start a new chat and ask something about it
[12:48] so let's say I ask it like
[12:50] hey
[12:51] what
[12:51] did we decide last month
[12:54] about the CRM or something like that
[12:57] right? It would need to
[12:58] like
[12:58] go
[12:59] and search all of these files
[13:01] to try and
[13:02] figure out what the right answer to this
[13:04] question is. And so I want to build
[13:05] something with Jeff here to see how we
[13:07] can improve this system
[13:08] because if we have Jeff here that's working in the background
[13:12] we can probably retrieve the memory in a much faster way
[13:15] and we can also do a better job
[13:17] in actually saving the memory
[13:18] Okay, here's what it built
[13:20] Let's have a look at that
[13:21] Okay, so again, it's this dashboard here
[13:23] and there are these tabs
[13:25] the first one says recall
[13:26] so this is probably where we can ask question
[13:28] and it recalls memory
[13:30] And it says here
[13:32] there's, you know
[13:32] we can type in our question here
[13:34] There are some examples that we can select
[13:36] which are questions that we can just use
[13:38] So I can just click one and say
[13:40] and the question here is
[13:41] what's the current offer positioning?
[13:43] So now it's doing the recall
[13:44] It's kind of waiting and asking Jeff
[13:46] Okay, so now it did the recall
[13:48] and it returned what you can see here
[13:50] So
[13:51] it says two thousand seven hundred fifty-six
[13:53] tokens versus
[13:55] thirteen thousand. So
[13:56] this request took almost eighty percent fewer tokens
[14:00] because we're using Jeff. And it says here
[14:02] the cost of this recall was
[14:04] zero point zero zero two nine seven dollars
[14:07] Okay, and, it answers the question
[14:10] So It was able to answer the question
[14:13] Okay, I asked for a quick explanation here
[14:14] So the way it was before
[14:16] Claudia's memory is a folder of Markdown files
[14:19] and the problem is that
[14:21] it's very inefficient the way the
[14:23] LLM is doing it. So it's basically
[14:25] when I ask a question
[14:26] it's like trying to guess
[14:27] which file the answer is in based on
[14:30] the title of the file
[14:31] So it's, you know
[14:32] doing a search for like keywords and file names
[14:35] basically. And then it's reading the entire file
[14:38] to
[14:38] see if the answer is actually inside of
[14:40] that file. And then
[14:41] yeah, it's basically hoping that it's right
[14:43] which is, you know, pretty bad
[14:45] And if it's writing memory
[14:46] it's actually even worse. So when the agent learns something new
[14:50] it should append something
[14:52] but it will never really know
[14:54] which file it should actually append it to
[14:56] And usually it will just
[14:58] I guess, append it to the daily memory file
[15:00] Yeah, so these are the problems
[15:01] Okay
[15:01] so how does it now work with the new system that
[15:05] now includes Jeff? So Jeff doesn't write text
[15:08] You give it some state
[15:10] which is A list of files
[15:12] a list of sections
[15:13] a new bullet
[15:14] and a batch of small typed questions
[15:16] Yes or no, pick one, score
[15:19] Okay, so these are like kind of the criteria
[15:21] and it answers all of them in one
[15:23] request in a few hundred milliseconds with probabilities
[15:26] Okay, so it's a judgment engine
[15:29] not a writer, and the code does the counting
[15:32] chunking, and diffing
[15:34] and Jeff only makes the small semantic calls
[15:37] So the way I understand it is
[15:39] with this new system that is using Jeff
[15:42] it's just able to
[15:44] much more easily find the right place where the memory is
[15:48] and it's kind of like doing this search
[15:50] like in parallel and getting like all of these data points
[15:53] and then it's able to pinpoint the
[15:55] right
[15:56] file where the memory is located much more
[15:59] efficiently and much faster. And so if we
[16:01] go back to the dashboard here
[16:02] we can try out a couple of other
[16:03] questions. So
[16:04] what broke between the CRM and the transactional
[16:07] email provider? So this is a very specific question
[16:10] Which, you know
[16:11] relates to something that I've done within my OS
[16:15] and it would need to
[16:18] like, search for the answer for quite a long time because
[16:21] you know, it would need to
[16:22] like, search through all of the files
[16:23] basically, or, like, all of the daily memory files
[16:26] maybe. So in this case
[16:27] it came back and it said 293 tokens
[16:30] versus 13,000. So
[16:33] 98% fewer tokens than it would normally need
[16:36] And the cost, also minimal here
[16:39] and the question was answered
[16:40] Okay, pretty cool
[16:42] what about this question? So
[16:44] what is Moritz's favorite pizza topping?
[16:46] The thing is
[16:46] I'm sure that I've never actually talked about this
[16:49] So this
[16:50] the answer to this question should not be
[16:52] inside of my OS
[16:54] inside of the memory files
[16:55] And you can see here
[16:56] it is missing. So
[16:58] you know, does the memory answer this?
[17:00] No. And for that reason
[17:02] actually, zero tokens were used
[17:05] which is 100% fewer tokens because
[17:08] you know
[17:08] it didn't even have to go and search
[17:10] the files. For this memory
[17:12] So it, it just knew that it doesn't exist
[17:14] which is
[17:15] pretty incredible. So this is obviously just an initial prototype
[17:18] and I'm sure there
[17:19] you know, you can still improve a lot about it
[17:21] but it's definitely a very interesting start
[17:24] and
[17:24] I think already an improvement to my existing system
[17:27] All right, so for my last example
[17:29] I wanted to build something that helps me
[17:31] predict whether a YouTube topic
[17:33] is going to do well or not
[17:35] and this is the dashboard here that I
[17:37] built. So I basically told it that it should
[17:40] like fetch a bunch of YouTube data
[17:42] and it's fetched like
[17:44] you know
[17:44] you can see here 600 videos
[17:46] in my niche across 15 different channels
[17:49] and it crunched all of that data
[17:52] and you can see like some of the analytics of
[17:55] you know, the, the data here
[17:57] I don't want to go too much into detail
[17:59] but if I click into this tab here
[18:02] it actually also
[18:03] gave me like a couple of interesting things here around some
[18:07] like, like feed, it
[18:08] it calls it feature importance
[18:10] So This one here
[18:11] for example, the duration minutes, how much
[18:14] so basically it's answering the question
[18:16] of how much does the duration of a
[18:18] YouTube video determine the success of it?
[18:20] And you can see the duration
[18:22] so the, the longer the duration
[18:24] the more successful the video is
[18:27] which makes a lot of sense
[18:28] right? So this is kind of what we're
[18:29] seeing on YouTube. Also
[18:31] live stream event seems to determine
[18:33] whether a video does well or not
[18:36] which also makes sense. They're pushing lives right
[18:38] now. Whether it's a course or a training determines that
[18:42] so it's, it's quite highly ranked
[18:44] And okay, so, so all of this is
[18:46] is pretty interesting data
[18:47] Now here is
[18:48] the part that actually gets useful
[18:50] So this is a score my title
[18:52] and
[18:53] the way it works is I can just type in my
[18:56] the title that I'm thinking about
[18:58] So let's say I'm thinking about the title for my
[19:01] for the ChatGPT course video
[19:03] the only ChatGPT
[19:05] work and codex course you need in 2026
[19:11] And then we'll do like two hours
[19:13] And then we can describe the concept here
[19:15] a creator pointing
[19:17] at a whiteboard with the curriculum on it
[19:22] And we can
[19:22] put in the planned length of the video
[19:24] here
[19:25] So we can put it as if it's
[19:27] going to be two hours
[19:28] let's put 120 minutes. And yeah
[19:30] then we can say score with Jeff
[19:31] Okay
[19:32] so it will come back with a score
[19:34] And you can see here the score
[19:35] it's, it's predicting a breakout based on this
[19:38] So because it's a course training
[19:40] it's, you know, has very high likelihood that this is
[19:43] this is going to do well
[19:44] So all of these indicators here would basically
[19:47] would basically push it towards doing well
[19:50] And these indicators here would
[19:52] like push it towards doing not so well
[19:54] So let's try a different one
[19:55] Let's just try like a super simple one
[19:57] like what is Jeff? And then we'll
[20:00] the thumbnail will say Jeff is insane
[20:03] And length of the video will be 20 minutes
[20:06] Okay
[20:06] so here
[20:07] it said it's going to be 0.35
[20:10] So it's going to be Underperformer
[20:11] If it's below 0.5
[20:13] it's going to be a underperformer
[20:14] What we can do
[20:15] here as well is
[20:17] here we can actually type in
[20:19] the topic for the next video
[20:20] So ideate, so this is the ideate feature and it generates
[20:24] featurize, ranks, and sanity checks
[20:27] So okay
[20:27] an LLM writes candidate titles and thumbnail concepts
[20:31] Jeff featurizes each one
[20:33] the model ranks them
[20:34] and the final Jeff choice over top five
[20:36] asks which
[20:37] viewer would click and which is
[20:39] the most honest. Okay
[20:40] And so
[20:41] let's just type in the topic of the next video
[20:44] which is Jeff tutorial and examples
[20:48] And then we can
[20:49] select like how many candidates we want
[20:51] So let's leave it at 15
[20:52] We click generate and rank
[20:54] And then now we can see here the
[20:55] LLM is now writing the
[20:57] title ideas and thumbnail ideas
[20:59] And then Jeff
[21:00] will do like a featurizing and ranking and
[21:03] a sanity pass
[21:04] So
[21:04] let's wait and see what it comes up
[21:06] with. Okay
[21:07] So it came up with
[21:08] a couple of things here
[21:10] So first of all
[21:11] Here it says Jeff's pick to click
[21:13] Jeff, tutorial for beginners
[21:14] build your first AI agent
[21:16] Okay. So it's
[21:17] it's basically the one that's ranked as number one here
[21:19] Jeff, tutorial
[21:20] build an AI research agent step by step
[21:22] And
[21:23] the driver's course or training offers signal
[21:26] clarity and then thumbnail high contrast
[21:30] Okay. And I'm guessing also because it's
[21:32] you know, I saw somewhere that it
[21:33] it's good when it's like specific
[21:35] So this is like very specific tutorial
[21:38] So maybe that's the reason that it chose
[21:40] this. AndThen it has like these
[21:42] these other suggestions. So it made fifteen suggestions
[21:45] right? The LLM made fifteen suggestions
[21:47] and then Jeff
[21:48] ranked them by which one would probably do
[21:50] the best. And then it says on
[21:52] in fifteenth position, I tried Jeff for seven days
[21:55] what it can actually do
[21:56] Okay. Interesting. I
[21:57] I don't know if I agree so much
[21:59] with these. I guess it's very hard to tell
[22:01] But yeah, this was, I guess, Jeff's ranking
[22:04] I do think this score my title feature is super useful
[22:08] so I might be using that
[22:10] But yeah, overall. Pretty cool
[22:11] All right, that's it for this video
[22:12] I hope it was helpful
[22:14] I find this new technology really interesting
[22:16] It was definitely just a start for me
[22:18] I will be experimenting more with it
[22:20] and inside of my school community
[22:22] I will be doing a couple of live
[22:24] sessions as well over the next week
[22:26] and to
[22:27] work together with other business owners to see
[22:29] how this can be implemented in their business
[22:31] and how it can be useful
[22:33] So if you want to join those
[22:34] definitely come check out my school community
[22:36] I'll put a link down below
[22:38] and otherwise
[22:38] hope to see you in the next video
[22:40] Bye-bye
