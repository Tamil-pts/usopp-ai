PROGRAM _CYCLIC
Motor1Cmd := (Step >= 1) AND (Step <= 3) AND DoorClosed;
Cylinder1Extend := (Step = 2) AND Motor1Running;
END_PROGRAM
