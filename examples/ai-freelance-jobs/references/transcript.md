# Transcript

[00:00] The number of one-person businesses built with GPT, Astra, and creative models are
[00:05] about to explode. That little combo of Astra and creative models is barely talked about,
[00:11] so today I'm going to show you a glimpse of that future and give away everything you need to build
[00:17] one of these businesses before everyone else does. These businesses are called AI-native service
[00:22] firms, and companies are already paying $500 to $5,000 or more on sites like Upwork or Fiverr.
[00:29] I'm going to show you how you can find those jobs and fulfill them using Astra from OpenAI
[00:35] and creative models like Flux and Kling. It's basically a semi-autonomous AI service
[00:41] firm. I'm going to walk you through how you can build it, the exact prompts you need.
[00:45] I'm going to give them away, and I'm going to show you something I built myself. By the end,
[00:49] you're going to understand what an AI native service firm is and why firms like Sequoia
[00:54] think there's a trillion up for grabs and how to start one yourself. At the end, I'm going to give
[00:59] you three startup ideas that you can copy and just go grab. This experiment is sponsored by
[01:05] Hicksfield. They funded the episode and supplied the API credits used to make it possible,
[01:10] so thank you. I wanted to see what you can build when one API connects you to a range of
[01:15] creative models. It's really cool, and that's the thing I'm going to show you. Let's get into it.
[01:28] So why do I think that there's going to be this explosion of one person businesses powered by
[01:34] models like Astra and creative models has to do with three things have become good enough at the
[01:40] exact same time. And that's why the explosion is going to happen. The first is creative models.
[01:46] It wasn't that long ago that we were all sharing that video of Will Smith eating spaghetti, that AI
[01:51] generated one, everyone was laughing at it because AI couldn't do creative models. But we've gotten
[01:59] to the point now, as of recording this, September 2026, that these models are pretty insane. You've
[02:06] got models like Kling, Flux, Seadream, and actually you've got dozens of these models
[02:11] that are just so good, so we're just no longer in that spaghetti phase anymore. The second is Astra.
[02:19] When Astra came out. I don't know if you've used it or not, but it's gotten to this point where you
[02:25] can build a operating system and actually it'll help run it. It could read a messy client request,
[02:31] figure out what's missing. It could plan the work, choose the right specialist model and keep
[02:36] track of the budget and inspect what came back and repair a failure. It can do all these things. And
[02:42] it just really feels like if you're a one person business, a model at the caliber of Astra is just
[02:48] so good. Of course, you need to supervise Astra and models like it. But it does really feel like,
[02:56] you know, this next layer, next level of AI models. And that's really cool. The third is
[03:04] now you have all these all these creative models, and they live in one production layer. You know,
[03:11] what do I mean by that? You know, in the past, you know, you had to open a dozen accounts, learn,
[03:17] a dozen APIs, move files between tabs, and try to remember which model made which asset. But now,
[03:26] last week, Higgsfield came out with their API, and you can just have all the models, all the pricing,
[03:32] all the requests, all the status, all the outputs behind one API. So when you combine all those
[03:37] pieces, you can actually build something that looks less like an AI tool and more like this
[03:43] small service firm that's actually fulfilled by AI. And that's kind of the dream, right?
[03:48] I know a lot of us want to build small, quote unquote, businesses, high margin businesses,
[03:55] businesses that we don't need to hire 50, 100 people. And you can kind of do that when you've
[04:01] got this combination of these three things. so you know when you can combine these three things
[04:08] you can have something like a customer ask for a video astra is going to run the job the creative
[04:15] models perform the specialized work and one person can handle like the contract and the taste and the
[04:20] rights and all that sort of stuff the other thing that i don't see a lot of people talking about is
[04:26] you can go to places like upwork Fiverr, Contra, or even just agency websites and just look at
[04:34] what people buy repeatedly, like product videos or localized campaigns or Amazon listing images. And
[04:40] if you pick one narrow deliverable, you package it up and teach the system, this operating system,
[04:48] how to produce it again and again, you don't really need to guess what people want to pay
[04:54] for anymore. You just have to give it the brief, give it the budget, give it the customer language,
[04:59] understand how the system works and build a system that works. And you're pumping out a machine
[05:06] that's creating good quality content. And that's why this opportunity is so large. So let me show
[05:11] you how you can actually build one, what it looks like end to end. Let's go check it out. Let's talk
[05:17] about the difference between a human agency versus a AI native service firm. What is the difference?
[05:25] What does it unlock? Where's the opportunities? And how do I think about it? So today we're going
[05:31] to be using the example of a creative agency. So creative agency, why creative agency is I've built
[05:40] them in the past, so I understand them pretty well. If you are building a creative agency,
[05:47] just a traditional creative agency with human beings, The way that you're going to get customers
[05:52] is going to be word of mouth. It's also probably going to be just like organic social, building
[06:01] a brand on social media. And that's basically how you're going to get leads. And those leads,
[06:12] you are going to get people to do the work. and the people that you're going to get to do the work
[06:20] is people. People do the work. Human beings do the work. And when they do the work, you, my friend,
[06:32] are going to get paid. How much are you going to get paid? You know, it's not crazy that the net
[06:40] margins at the end of the year are in the 10 to 15 percent net margins. Why is it so low?
[06:50] It is so low because finding people, paying them competitively is tough. People leave,
[06:57] you have to replace them. And it's also hard to do marketing over here to get customers into the
[07:06] door on an ongoing basis. Now, what does an AI native firm look like? Well, the AI native
[07:18] firm unlocks a sales channel that was otherwise just out of reach. So an AI native creative firm
[07:26] can still do word of mouth, still can do organic social. But it has one more thing it could do.
[07:32] It could go to marketplaces like Upwork, Fiverr, things like that online and ingest projects and
[07:46] needs that people have and go and fulfill them. These were traditionally lower cost work, things
[07:54] that are $100, $500, $1,000, $5,000, $10,000, $25,000. But you can do them because the margins
[08:03] are going to be a lot harder, higher, not harder, when you're creating an AI native creation shop.
[08:11] Because who is doing the work here? Well, you can have something like Astra creating the operating
[08:20] system of how you actually get things done and orchestrating. You can have something like Higgs
[08:27] field, which manages one API for all the creative models to actually create the work. And together,
[08:40] plus a small amount of people, could even just be one person, you do the work. And the
[08:48] person approves the work. You know, this is not a fully autonomous company. It's a semi-autonomous
[08:55] company. A lot of people talking about how, you know, autonomous companies are here.
[08:58] They're not really here, but they're close. So it's semi-autonomous. I don't think it's crazy
[09:05] that this bumps up to 60 plus percent net margins. Because the work that you can do here on a gross
[09:13] margin level could be 70, 80, 90, 95 percent. And that's what we see today with some of the things
[09:20] that I built. And, you know, I think that this is just an example, just in a high level, you know,
[09:26] and there's obviously a lot of differences between human agency and AI native service firm. But one
[09:31] is sales channels that have been out of reach are now in reach. Price points. Let's talk about let's
[09:39] talk about what's different in human versus AI native. So we have sales channels now unlocked
[09:49] new ones. you have a true loop of a business. What do I mean by that? I mean that if you're
[09:59] a creative agency and you learn over time and learn over time and you gain these lessons,
[10:04] the problem is you have people doing the work. So those people leave to other places. So you lose
[10:08] those lessons. If you create a loop over here, you're constantly learning and you're getting
[10:13] better and you're able to create creative that's better and better and better and better at higher
[10:19] margins. higher output, less mistakes. So because this is truly, you know, digital first, AI first,
[10:27] there's that loop there. You do have a true loop of a business and easier to manage. Now, I don't
[10:35] think creative agencies, you know, are going away. You'll still have people, human created
[10:40] agencies doing stuff. I think that over time, they're going to adopt a lot of what's happening
[10:45] here in AI native land. But I think this is just, you know, an example of how to think about, okay,
[10:52] what is a new way of doing business looks like? And what are the outputs that come from it? What
[11:00] are the results that come from it? Why should I be doing it? More margins, easier to manage,
[11:06] potentially higher exit multiples because it's more software oriented. human agency versus AI
[11:13] native service firm. So this is Studio Operator, and it's basically your cockpit for running AI
[11:22] creative service work. You can see all the active jobs you have. Okay, 25 jobs, pipeline value is
[11:29] $3,400, estimated growth profit is $3,200, and there's 17 projects that need my attention. And
[11:37] the end state of this is you're going to have you're gonna have all these inputs for jobs that
[11:41] are coming in from places like Upwork, Fiverr, you know, direct leads. You're gonna go and search for
[11:50] these opportunities, you're gonna put them in here, and then you're gonna have AI actually
[11:54] complete the work. That what this is You know if you go to Upwork there literally hundreds of
[12:04] thousands of jobs or thousands of jobs of people willing to pay between and for different projects
[12:13] And you can go and just copy and paste those into here and go and do those projects with something
[12:19] like Studio Operator. If this episode gets 5,000 likes and comments, we've had many videos on the
[12:24] channel. luckily get to that number, I'm going to give away Studio Operator. I'm just going to have
[12:30] it so that any one of you can go and duplicate it and actually run one of these businesses. You'll
[12:36] just have to copy and paste and you can go and build it. So let's see the comments and likes
[12:42] roll in and I can't wait to give it away. So let me show you how this works. Here I'm in the QA
[12:51] phase with this. This is an interesting one. So say someone wants to launch a new blood orange
[12:59] aperitif. You can see a direct lead over here. So it's not coming from Fiverr or someone like that,
[13:07] but someone's like, hey, I want this. I go and create the client brief. If it was from Fiverr
[13:12] or Upwork, I would just upload the link here and Astra would go and extract all that data
[13:19] and create the client brief, create the reference assets, and create the client notes. It goes and
[13:25] reviews all that brief and basically says, like, okay, what are the deliverables going to be? It's
[13:33] going to be in PNG. We want it to be three by four ratio. Are there any questions for the client? So
[13:39] this is basically productizing the operations of the actual job to be done. You can even say like,
[13:47] hey, I don't want to spend more than five cents as a production budget. And, you know, as you
[13:53] can see in this product, minimum gross margin and gross margin and profitability is really, really
[13:58] important to me for this. Because I'm looking to create, you know, creative that's going to get me
[14:05] 70, 80, 90 percent plus margin. You can see here the client was willing to pay ten dollars. I have
[14:14] Astra actually give me a estimate based on what Higgs field is going to actually go and create
[14:21] one cent here. So my expected profit is going to be $9.99. You know, if I can do that,
[14:27] I want to do that all day. And then you can see here's the workflow. So it went and
[14:34] looked into my model router. so what's really cool is Astra built a model router with Hicksfield that
[14:41] basically says like oh hey you know this model is good for this this model is good for that
[14:46] and it goes and creates the best possible possible stuff here you know you can even propose a visible
[14:53] production route over there and this is what it looks like you know to me this looks really
[15:01] just breathtaking, honestly. This is really cool, interesting, actually pretty scroll-stopping. And
[15:10] it did a good job. And it did a good job because of the model routing. It did a good job because of
[15:14] the brief. It did a good job because of just the workflow that we've been able to do. And
[15:18] then there's a place for revisions as well. And if I like this, it comes to me on my main feed,
[15:26] and it's ready, and it's in QA. I can just approve delivery, and I'm done with it. Good to go.
[15:36] And I didn't add this to send the files to your client manually, but in the future, I can just
[15:42] automatically have Astra send that. How insane is that, right? You're grabbing the validated demand
[15:50] that exists on the internet. You're putting it in here. You're able to actually create high-quality
[15:55] creative that looks good, that feels good. you have that human layer too. For some people who
[16:02] want to go completely autonomous, go for it. I think we're going to get there over the next 12,
[16:08] 18, 24 months. But right now, I do think having a human being go and looking at some of the stuff
[16:15] is important. I'm going to show you just a couple more things here, just because the output is
[16:24] insane. Again, the aperitif, a five second video, you can see here the client willing to pay $10,
[16:33] about a 70 cent estimation of what it would cost. And it's important to have that because before you
[16:40] hit go, you don't want to, if the expected margin is 1.6% instead of 91.6%, you might not click it.
[16:48] It also included a channel fee because Fiverr, I think, charges 5 to 15% or Upwork charges 5
[16:56] to 15%. These marketplaces, you know, charge a contingency channel fee. So you're going to want
[17:01] to include that there. You can see the human checkpoints over here and the activity. This
[17:07] just shows me like what has happened. Like all, here's all the generations. And I can just go and
[17:14] as a human being, you know, just look at this and be like, okay, yeah, this makes sense. This makes
[17:21] sense or this doesn't make sense. So overall, you know, just a, just a really, that's why I said it
[17:28] was a glimpse into the future because something like this, or, or more and more things like this
[17:34] are going to exist. And I'm just surprised that more people aren't doing, aren't doing this.
[17:42] other things I can show you, like there's this autonomy section, which I think is
[17:46] really important. I might not want to spend more than $10 per job or $100 per job. Or one of the
[17:53] reasons why agencies really get killed on margin is repairing things. So you might want to say 50
[18:01] cents per repair or maximum attempts per step. You can have certain model families that you like
[18:08] and don't like. Hey, maybe you don't want to use any Chinese models. So you're like, I don't want
[18:14] to use Quinn or something like that, or C-Dense, you know, you decide, and you can actually have,
[18:22] you know, all the client communication stuff here and the client account memory, right? So like, oh,
[18:28] we have a customer called Moro Coffee. Here's their name. Here's their logos, their colors,
[18:35] their fonts, what they like, rejected styles, like all their stuff will be included here, just like
[18:42] a real agency. So it's a real agency, except the stuff gets done by AI. Astra is like the
[18:51] orchestrator with Higgs field. And the output is really good. You know, it's like, it's shockingly
[19:01] good. And it's got memory. And, you know, the hardest part then becomes going and searching for,
[19:08] you know, what are the interesting projects on places like Fiverr and Upwork or creating your own
[19:18] brand and getting people to come to you. Maybe you start an X account or an Instagram account and,
[19:25] you know, you say like, I do logos for $10. and you just maybe the growth strategy is you redesign
[19:34] other people's or famous logos. And then you say like, oh, hey, and I'll do a logo for you for $10.
[19:41] And you can just Venmo me or whatever, right? Like things like that and getting a lot more direct
[19:48] leads might be better, right? Because you don't have to pay the channel fee and you're building
[19:53] more enterprise value. So I think this is really interesting. I honestly was shocked with how good
[20:01] it was. And there you have it. This is a tour of Studio Operator. Let me give away the six prompts
[20:10] to actually go and build this using Astra and the creative models. So I built this product with six
[20:17] prompts, and each prompt added one layer of the firm. I'll explain what I asked for, and I'm
[20:23] going to show you what it created Instead of just reading the instructions line by line, I'll just
[20:28] give you the high level of what I asked for. And I'm giving away all these prompts in the link in
[20:33] the description. You can go and grab that if you want to create something like this on your own.
[20:38] So the first prompt, the build the firm prompt, it basically created the shell of the business.
[20:45] So I asked Astra to build an actual operating system instead of another chat window. So I
[20:52] wanted service templates. I wanted a job inbox. I wanted production stages. I wanted client records.
[20:58] I wanted deliverables, costs, margins, approvals, revisions, and delivery. As someone who's run
[21:03] agencies before, I knew I needed all those things. Every job needed a clear state and a next action.
[21:10] So a semi-autonomous firm needs somewhere to store what happened, what was approved,
[21:17] what it spent, and what still needed a person. So that would be the foundation, and that was prompt
[21:23] number one. So the second prompt teaches Astra how to turn messy demand into a job so that it
[21:31] can actually run the job and we can get paid. So it reads an unstructured marketplace brief,
[21:37] like if it's coming from Upwork or Fiverr or one of those, and it extracts the deliverables,
[21:41] it extracts the formats, exact copy, the deadline, the supplied assets, the missing inputs, the risk,
[21:48] and the likely revision problems. which is really important because that's going to affect margin.
[21:55] It drafts the smallest useful set of client questions and it recommends whether the job
[22:00] should be accepted, reviewed or rejected. And Astra is going to handle the judgment here and
[22:05] the normal code is going to handle the price and the margin calculations. Once we have that,
[22:11] that's when we can actually connect it to Higgsfield to get the creative models, right?
[22:15] So the third prompt connected the Higgsfield API as the production layer. So OneKey opens
[22:23] a catalog of more than 50 images, videos, audio models, and workflows, which is really cool. And
[22:29] Astra can route work across C-Dance, Kling, Sol, Recraft, and the rest of them without separate
[22:37] provider integrations of each one. So HiggsField is basically the harness around those models.
[22:43] It handles the queuing, the GPU scaling, the shared submit, check, download flow, and exposing
[22:49] public pricing and cost estimates before each generation run, which is important because we
[22:57] want to keep our gross margin high, 70%, 80%, 90%. The key stays on the server, and every request,
[23:05] result, failure, and actual charts stays attached to the client job. The fourth prompt is going to
[23:11] build the model router because we're going to need the system to basically go to the right creative
[23:20] model so we get the best output. So the fourth prompt turns the Higgsfield model catalog into
[23:26] this production system. So Higgsfield provides the models and the workflows and the pricing
[23:30] and the execution layer. And I wanted Astra to decide which model fits each step and actually
[23:37] explains why. So I have it actually explain why in Studio Operator. I did add a feature where I can
[23:46] override asterisk choice and immediately see how that changes the job economics. Prompt 5
[23:53] is adding quality insurance and repair. So it gonna be all in charge of correcting things
[23:59] So every output gets checked against the approved brief for the right format duration copy product
[24:06] details required scenes brand rules motion audio and anything else the client going to approve So
[24:14] the system decides whether the asset is ready or it needs a controlled edit or it needs to be
[24:19] regenerated or it needs a human decision. you might be wondering why some of the outputs on
[24:27] Studio Operator look so good and it's because the QA is really part of it is the QA is really good
[24:35] look at this, this is absolutely stunning this is for a perfume brand but just looks really
[24:44] cool and it's got a lot of good aura and a part of that is because of the QA prompt So don't forget
[24:51] that. The sixth prompt adds the controls that lets the autonomous firm keep moving safely. So
[24:58] each job has spending limits, repair limits, maximum attempts, approved models, rules for
[25:04] client messages, and a clear approval gates. So Astra can draft updates, interpret, you know,
[25:12] routine feedback, which is really cool. Remember the client's preferences. There's a whole area
[25:17] for the memory on Studio Operator. Look at major scope changes and final delivery come back to the
[25:24] human that we can actually approve. The audit log records every decision, generation, cost, change,
[25:32] repair and everything. You can just see all the activity that happens, and that was important for
[25:38] me because I want to make sure that the stuff that gets delivered is high quality, and if there is
[25:44] some mistake, I can trace back to it. The orders of the prompts do matter a lot. I gave Astra the
[25:53] business one layer at a time. You know, what we sell, how a job moves, how production connects,
[26:00] how models are chosen, what correct means and which decisions require a person. And then I
[26:06] put it together. It's not like I just gave it all at once. And I think you're going to get a better
[26:11] result if you do that. Once those six layers exist, changing the service template creates an
[26:17] actual different firm. So a launch video template can become like a whole podcast promotion pack.
[26:22] Maybe it becomes a real estate listing pack, a monthly restaurant content service, these sorts of
[26:29] things. The interface doesn't really change, but the buyer, the deliverable, the production recipe,
[26:35] the rulebook, and the approval points could change. And that's what you want because you're
[26:40] going to have different types of clients come in. Okay, so I've shown you Studio Operator how to
[26:45] take a job from Upwork or Fiverr, take it through production, repair and delivery. but there's so
[26:52] many creative models and I don't know about you, if you're anything like me, you're just like,
[26:58] what model is each good at? And I know that you have Astra orchestrating the thing and routing the
[27:06] models, but it's important that if you're going to do this, you understand what each model is good at
[27:11] and what it's bad at. So before choosing a model, I ask four things. Am I making a still image,
[27:18] a video, or something with speech? Am I creating something new or repairing an asset that is
[27:24] already close? Am I exploring new ideas cheaply or am I making the final version? And what absolutely
[27:31] cannot change? The product, the person, the words, or the movement? Once you answer those questions,
[27:37] the model choice becomes a lot easier. So we're going to go through just a primer of all these
[27:42] different models. You've heard their names. By the end of this little section, you're going to
[27:46] understand what you should use and when you should use it. If the job is a person and the image needs
[27:53] some amount of taste, I would use soul. It's really good for fashion and editorial images,
[28:00] identity, and it's got these culturally current portraits and founder photo shoots. But the weak
[28:08] spot is things like packaging, logos, and small legal copy, so it handles those in a separate
[28:15] step. if the job is like a product scene, see Dream or Flux. They're really good at taking
[28:22] one clean product reference and placing it into different lifestyle images or campaign worlds
[28:30] while keeping the subject recognizable. But I will watch out. I would give you a few watch
[28:35] outs. So labels, the exact colors, sometimes like small geometry. You need to check those against
[28:44] the original product. If the creative asset needs real words and layout, ideogram or
[28:52] recraft are going to be your best bet. So that's the lane for posters, covers, local promotions,
[28:59] campaign graphics, and other design assets where typography is part of the product.
[29:06] Obviously, I'm not going to go reach out to ideogram if I'm trying to do cinematic motion
[29:12] and things like that. If the image is already good, but like one detail is wrong, when? So it's
[29:20] really good at repairing a label or replacing one object, localizing a headline, or correct like one
[29:28] small visual mistake, but you want to preserve everything else. So I use it as like a repair
[29:33] shop, but not a place where I want to develop the entire creative direction. for cheap still image
[29:41] exploration zimage and marketing studio image can produce a lot of directions quickly you know for
[29:48] cheap video explorations pixverse the faster wand models and lower cost cling configurations can
[29:54] test hooks openings and camera ideas their job is help you decide what is worth making properly
[30:01] so don't confuse the most interesting tests with the final deliverable. If the job is a
[30:06] longer cinematic scenes, I would use C-Dense. It becomes useful when you need multiple references,
[30:14] a sequence that develops over time, native audio, or the ability to edit part of the result. It is a
[30:21] stronger production model once the direction is clear, rather than the model I would use for 30
[30:26] random experiments. If the job is the hero shot, I'd use clang. That's where it's been more for,
[30:33] you know, camera movement, physical realism, and that final touch that you know that the customer
[30:38] is going to notice. There are more expensive ways to discover that the original idea was weak, which
[30:44] is why I would arrive at the shot already planned. If the person needs to speak and the audio should
[30:50] be generated with the scene, Juan or Minimax. They're useful for creative ads, spokesperson
[30:58] videos, localized performances, but I would watch out for lip syncing, logos. Those things need a QA
[31:06] pass from them. If you already had the exact movement you want, I would use Kling Motion
[31:11] Control. So you give it the movement reference and apply that performance to a person or character,
[31:17] which makes it really useful for things like fitness, dance, demonstrations, and repeatable
[31:23] creative formats. Think about it. If you figure out the format, you give it to Cling Motion
[31:29] Control, and it's pretty darn good. The source image and motion reference have to be clean,
[31:36] though, because bad inputs do become part of the output. Then I would use Topaz, LipSync, voice
[31:46] captions, and export tools to finish the work. So these tools improve resolution, they localize and
[31:51] improve performance, and create the actual files the customers want to publish at the end of the
[31:56] day. So they can publish a good asset, but they're not going to rescue a bad concept. I will say,
[32:03] I wish the Higgs field API had nano banana. Wish it had it, it doesn't have it. So the way to
[32:10] think about all these models, Sol is for creating people, designing people. SeaDream and Flux are
[32:18] for products. Ideogram and Recraft are for words and layouts. Quen is your repair shop. SeaDance
[32:24] is for those longer scenes. Juan and Minimax are for speaking. Motion Control is for copying
[32:32] or performance. And Topaz and Finishing Tools get the work done to deliver. That's basically
[32:36] the primer of if you're using Higgs Field Launch API, those are the best ones to be using. Okay,
[32:43] so I'm going to give you three startup ideas that are all about this whole AI native service firm
[32:50] that you can build with Astra and you can build with these creative models, run them end to end.
[32:55] I hope people build them. And if at the very least just get your creative juices flowing, let's go.
[33:00] So the first one is an always on ad studio. So every e-commerce brand has the exact same problem.
[33:09] The ads get tired faster than its creative team can replace them. So I would sell a weekly
[33:16] creative pack for one SKU. So the brand gives you the product page, the original photography,
[33:22] the brand rules, and the approved claims. And then every Friday, it receives new hooks and product
[33:29] scenes and still ads and short videos that are just ready for the media buyer to test. You can
[33:35] call it something like Friday ads or something like that. And then the production system is
[33:40] pretty simple. You can have Astra reading the product pages, the reviews, social, current ads,
[33:48] to find languages, to find the language that buyers are already using. And you can, you know,
[33:52] you'll use that for the basis of your ads. Cheap models explore 20 angles before you spend real
[34:00] money on them. So customers are going to be happy about that. You can use like Flux or C-Dream to
[34:07] keep the product consistent across the strongest scenes. Then you can use Quinn as the repair shop.
[34:13] Things are going to need help on packaging and copy. And then faster video models test movement,
[34:20] right? And premium models produce the few ideas worth putting in front of customers. So you have
[34:26] QA comparing the label, the colors, the claims, the formats, and the required shots with the
[34:32] source assets before anything leaves the system. If I was starting this tomorrow, I would choose
[34:38] one category and build a list of like 100 brands. I'd probably open the meta ad library and look for
[34:46] companies that are clearly spending money but have not a lot of creative variety. It looks all the
[34:53] same. It's like the same product hook, the same background, around one or two or three formats
[34:59] across most of their active ads. Then I would be looking at their reviews, their five-star reviews,
[35:04] even their one-star reviews to get some insight around how can I test a bunch of different hook
[35:10] angles. For the best prospects, I would make three private watermark concepts and record a
[35:16] 90-second loom. And the pitch becomes, hey, you have this really good product, but most of your
[35:22] ads are making the same argument. So I've got these three unused hooks from customer reviews,
[35:30] and I mocked up what they could look like. You're actually showing them the work, and you're showing
[35:38] value. And then I would sell the first engagement as a paid creative sprint for just one SKU. Maybe
[35:46] you charge like $750 to $1,500. Depends on how many deliverables they want. And then once
[35:54] something performs you can move the brand into a monthly package where you get that batch every
[36:00] week and you getting that recurring revenue I would say like a really interesting growth tactic
[36:06] for this business is media buying agencies So they already have clients who need more creative. And
[36:15] if you can be and if you can build a production layer that plugs into the account, that's super
[36:22] valuable. And then you're learning in real time. you're building this library of hooks and failure
[36:27] patterns and winning creative structure that Astra then could reuse without making brands look the
[36:33] same. That data is really, really powerful. That's a good one. It doesn't require a lot
[36:40] of money to start. I like the monthly recurring revenue. I like that you're validating because
[36:48] it's validated because these people are spending money already. The big if is if you could create
[36:55] actually good ads. And I believe what I showed you today with Studio Operator, you can. The second
[37:02] startup idea is one of those boring business ideas that some people might really like. So
[37:08] franchises. A franchise might create one good national campaign and then they need 50 local
[37:16] versions with different addresses, prices, offers, languages sometimes, phone numbers, all that sort
[37:23] of stuff. So the way it works is today, someone at like HQ or they're in an agency they work with,
[37:30] they rebuild the same thing over and over. That is a beautiful job for an AI native service because
[37:38] the creative direction is already approved. The remaining work is repetitive and it's checkable.
[37:45] So how do you build it? Well, the client uploads the approved master campaign, the brand rules,
[37:52] and a spreadsheet of all the locations. Then you have Astra create the production plan and
[37:58] keep every location's data attached to the right asset. You have Quinn and Ideogram and Recraft
[38:05] handle copy and layout changes. Voice and lip sync models create the approved language versions. And
[38:11] then QA checks every address, price, offer, phone number, and disclaimer against the spreadsheet
[38:18] before you actually deliver the stuff. I would target brands in the 20 to 200 location because
[38:26] they're big enough to feel the pain every month, but the marketing team is still reachable. You're
[38:33] not going after McDonald's here. the internal the the international franchise association directory
[38:43] actually low-key gives you a brand list and linkedin gives you the head of franchise marketing
[38:49] the local store marketing or brand operations you can also by the way look at the brand's location
[38:54] page and social accounts to see whether each franchisee is improvising its own creative or have
[39:02] ai do that for you too just going and checking that with browser use. Okay, so how do you think
[39:08] about outreach? How do we get customers to this idea? Take one public national campaign and just
[39:15] privately mock up how it could become three local versions. You have the real store information,
[39:22] you watermark everything, and then you send a before and after video. And the pitch is like,
[39:28] hey, you've got this amazing national campaign. Here's what the approved creative could look
[39:34] like for Miami, Austin, and Montreal without asking a bunch of teams to rebuild it. And you
[39:41] come in there undercutting agencies by so much, right? You have so much more margin to play with.
[39:49] And it's like, did you know you can get it for $500 a month? I would start with a paid five
[39:55] location pilot. The point is to brew that after every address, offer, phone number, language,
[40:02] and disclaimer survives the workflow correctly. They want to make sure that this actually works.
[40:06] And once it works, price the service per location, per campaign, or as a monthly localization desk.
[40:15] So the expansion is built into the account, right? Five locations become 50, one campaign becomes
[40:21] the monthly calendar, and then one language becomes four. And then you sell it through
[40:25] the ecosystem. You know, there's franchise marketing agencies or multi-unit operators,
[40:30] someone who owns 20 Chick-fil-A's, you know, print vendors and private equity firms, you know,
[40:35] who actually have like a bunch of brands with the exact same problem and are looking to reduce
[40:41] costs. The cool thing is one agency relationship or one of these relationships can bring you 10
[40:47] franchise systems. And then you're just like built into their system. Everyone's happy.
[40:51] They're paying less. You're producing good work. And the customers aren't getting campaigns that
[40:57] are not in their language or aren't catered to them. The third startup idea is how can you turn
[41:04] an industrial catalog into a sales team? Let me explain what I mean by that. There are thousands,
[41:10] yes, thousands of manufacturers who are selling expensive products with dense PDFs, bad photos,
[41:18] and product pages that look like they were last touched in 2009 because they probably were last
[41:23] touched in 2009. The service turns one SKU into a short product demo, an application video, a trade
[41:30] show loop, a distributor training clip, and a set of sales graphics. How do you build it? Well,
[41:37] you get Astra to read the spec sheets. You get those CAD files, the manuals, the approved claims,
[41:43] and that turns into a visual plan. The creative models show the product in the environments
[41:49] where it is actually used. You know, while the rulebook checks every dimension and feature and
[41:54] compatibility claim and safety statement against the actual source material. So the customer gets
[42:00] a useful sales package and they don't have to arrange this new shoot for every SKU,
[42:05] which is actually a pain point. If I were going to do this, you want to start with one vertical. You
[42:11] know, maybe it's commercial kitchen equipment or dental labs and just learn its language.
[42:17] You know, ThomasNet has hundreds of thousands of manufacturers and suppliers organized by category.
[42:25] And trade show exhibitor lists are another ready-made prospect database. Look for a company
[42:31] selling a five-figure product with a detailed spec and product page. And it has three dim photos and
[42:39] no useful video. You know, the worse the marketing looks, you know, besides the price of the machine,
[42:44] the stronger the lead. And I can tell you, no one on X is building something like this. These people
[42:54] want something like this. And then you start with one SKU and you expand to multiple SKUs over time
[43:01] as they do new product launches or customized versions of their products. So you're building the
[43:08] sales assets for them in real time. It's actually another boring idea that I think could print. So I
[43:16] gave you four business ideas. I gave you studio operator. I gave you three more startup ideas,
[43:21] but there are probably hundreds of versions of this hiding across different industries.
[43:26] The harder question is how do you decide which one is actually worth building? So I would start
[43:33] by making a list of repeated jobs from Upwork, Fiverr, industry directories, and agencies that
[43:40] serve a niche. Then I would ignore how exciting the industry sounds, and I would actually just
[43:46] look at the shape of the work. So I would use four filters. The first filter I would use is,
[43:52] does someone actually pay for the work already? An existing budget is way easier to capture than
[43:59] a completely new category to explain. The second, well, the unit has to be obvious. One SKU pack,
[44:08] one localized campaign, one product video, or one listing package is easier for the customer to buy
[44:14] and it's easier for the agent to understand. The third is just the work repeat. You know,
[44:21] repetition gives the workflow a chance to improve and it gives you a reason to sell
[44:26] a subscription or an ongoing product or contract so you're getting paid monthly. Then you can quit
[44:32] your job or just you've built something with a lot more value in terms of exit value. Meaning
[44:38] when you have recurring revenue, that business is worth a lot more than something with one time
[44:42] revenue. And then the fourth is, is there a concrete definition of correct? So obviously,
[44:51] creativity and creative taste can be subjective. But what can't be subjective is the product name,
[45:00] the SKU number, the claims, the formats, and the required scene that can all be checked. So the
[45:07] strongest opportunities, in my opinion, have a creative surface, but a boring operational
[45:15] core. So the customer notices the campaign or the film. The company makes money because it
[45:23] controls intake, cost, versioning, rights, QA, and delivery. Every job leaves behind a useful
[45:31] lesson. Which missing input predicts revisions? Which model preserves the important detail? Which
[45:37] route stays inside the margin? And which beautiful output fails the client's actual requirements? But
[45:44] over time, those lessons become the software. And that's what's so cool about this age of building
[45:51] AI native service firms is you're building a loop. And in the past, you're building a loop
[45:57] around human beings, but human beings would leave, right? If you started an agency and over time,
[46:02] your agency would get smarter and smarter, but those people would leave. and because of that,
[46:09] they went to other places and those lessons went to other places. With an AI native service firm,
[46:14] you're building this loop and it's getting better and better and better. The more client work you
[46:19] do, the more outputs you generate, the more lessons you learn, the more workflows you do. It
[46:25] really is a new way of doing business and that's what's so exciting to me about this age we're
[46:32] in where you can have Astra plus these high-end creative models. Creative AI is finally reaching
[46:38] the point where you can build a company around it. The models are becoming specialists, and the APIs
[46:46] make them programmable. And Astra and models, whatever Claude and Google and others are going
[46:53] to come out with, can run the messy work between the client request and the final delivery. If you
[47:00] want to start a business or if you're interested in this, I would start with one narrow package
[47:05] and then five customers. You want to stay close to the work, write down every missing input, mistake,
[47:10] revision, and place the margin disappeared, and then turn those lessons into the intake, into the
[47:18] routing, into the QA, and into approval rules. So you get paid, basically, while you're discovering
[47:23] what the software needs to become. I think the next wave of one-person businesses will look like
[47:31] these small, capable companies that happen to have most of their staff inside workflows like this,
[47:37] this AI-native workflows. So I hope this got the creative juices flowing. This is an incredible
[47:44] time to be building. Like I said, I haven't seen too many people talk about this in this way. so
[47:51] my goal with all these things is just to help you connect the dots hopefully a light bulb or
[47:58] two go off and if I do that then I've done my job I'll see you next time have a creative day
