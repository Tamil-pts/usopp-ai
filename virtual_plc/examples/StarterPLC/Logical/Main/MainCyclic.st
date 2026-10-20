PROGRAM _CYCLIC
(* Training logic only. Commands and outputs share the virtual memory. *)
MotorRunning := StartCommand AND NOT StopCommand AND DoorClosed;
IF ResetCounter THEN
    ScanCounter := 0;
ELSIF MotorRunning THEN
    ScanCounter := ScanCounter + 1;
END_IF;
END_PROGRAM
