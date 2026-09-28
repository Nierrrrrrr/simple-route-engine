package dev.routeengine.api;

public class ApiProblem extends RuntimeException {
 private final int status;
 private final String code;
 private boolean suppressRequestId;
 public ApiProblem(int status,String code,String message){super(message);this.status=status;this.code=code;}
 public ApiProblem withoutRequestId(){suppressRequestId=true;return this;}
 public boolean suppressRequestId(){return suppressRequestId;}
 public static ApiProblem unsafe(){return invalid().withoutRequestId();}
 public int status(){return status;}
 public String code(){return code;}
 public static ApiProblem invalid(){return new ApiProblem(422,"INVALID_REQUEST","Request does not match the supported schema");}
 public static ApiProblem conflict(){return new ApiProblem(409,"STATE_CONFLICT","Resource state changed or action is incompatible");}
 public static ApiProblem missing(){return new ApiProblem(404,"NOT_FOUND","Resource not found");}
}
