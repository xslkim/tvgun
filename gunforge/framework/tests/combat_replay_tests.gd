extends SceneTree
const Loader=preload("res://core/level_loader.gd")
const Session=preload("res://core/level_session.gd")
const Codec=preload("res://core/pose_codec.gd")
var failures=[]
func _initialize():call_deferred("run")
func run():
	var path="";var assets="";var recording="";var report=""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--recording="):recording=arg.trim_prefix("--recording=")
		if arg.begins_with("--report="):report=arg.trim_prefix("--report=")
	var model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(path)),assets)
	if model==null:quit(2);return
	var session=Session.new();session.setup(model)
	var file=FileAccess.open(recording,FileAccess.READ);var tape=file.get_var(false);file.close()
	session.load_recording(tape)
	var samples=[109,200,305,840,1200,2000,2500,2515,3000,3301,4000,4920]
	var states={};var poses={}
	while session.clock.tick<tape.end_tick:
		session.step()
		if session.clock.tick in samples:
			states[session.clock.tick]=var_to_bytes(model.save_state())
			poses[session.clock.tick]=var_to_bytes(Codec.encode(model.geometry(),model.geometry_assets()))
	if model.result!="clear" or model.resources.purified!=29 or model.resources.rescued!=1:failures.append("recording_did_not_preserve_complete_result")
	var final=var_to_bytes(model.save_state())
	var seek_ms=[]
	for at in [4000,109,3301,305,2515,1200,4920,200,3000,840,2500,2000]:
		var began=Time.get_ticks_usec();session.seek(at);seek_ms.append((Time.get_ticks_usec()-began)/1000.0)
		if states[at]!=var_to_bytes(model.save_state()):failures.append("state_at_"+str(at))
		if poses[at]!=var_to_bytes(Codec.encode(model.geometry(),model.geometry_assets())):failures.append("geometry_at_"+str(at))
	session.load_recording(tape)
	for i in range(tape.end_tick):session.step()
	if final!=var_to_bytes(model.save_state()):failures.append("complete_replay_differs")
	var output={"passed":failures.is_empty(),"failures":failures,"build_id":model.build.build_id,"seek_samples":samples.size(),"seek_ms":seek_ms,"scope":"full real combat package, bound-input binary replay, art geometry, local clocks/effects/cues/resources"}
	if not report.is_empty():FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(output,"\t"))
	print(JSON.stringify(output));quit(0 if failures.is_empty() else 1)
