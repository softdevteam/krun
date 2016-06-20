def run_iter(param)
	begin
		if (not Truffle::Graal.graal?) then
			raise "Graal is not enabled"
		end
	rescue NameError
		raise "Failed to find Truffle::Graal.graal? attribute."
	end
end

if __FILE__ == $0
	run_iter 666
end
