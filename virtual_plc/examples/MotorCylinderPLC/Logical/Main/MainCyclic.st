PROGRAM _CYCLIC
(* Training sequence. START is an explicit operator event. Feedback comes from the plant. *)
IF StopButton OR NOT DoorClosed THEN Step := 0; END_IF;
CASE Step OF
    0: IF StartButton AND DoorClosed AND Cylinder1Retracted THEN
           CycleComplete := FALSE; Step := 1;
       END_IF;
    1: IF Motor1Running THEN Step := 2; END_IF;
    2: IF Cylinder1Extended THEN Step := 3; END_IF;
    3: IF Cylinder1Retracted THEN CycleComplete := TRUE; Step := 4; END_IF;
END_CASE;
END_PROGRAM
