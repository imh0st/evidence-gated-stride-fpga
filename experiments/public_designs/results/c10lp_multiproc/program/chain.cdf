JedecChain;
	FileRevision(JESD32A);
	DefaultMfr(6E);
	P ActionCode(Cfg)
		Device PartName(10CL025YU256) Path("G:/2026_CS/git_upload/build/public/c10lp_multiproc/") File("top_level.jic") MfrSpec(OpMask(1) SEC_Device(EPCQ128A) Child_OpMask(1 7));
	P ActionCode(Ign)
		Device PartName(VTAP10) MfrSpec(OpMask(0));
ChainEnd;
AlteraBegin;
	ChainType(JTAG);
AlteraEnd;
