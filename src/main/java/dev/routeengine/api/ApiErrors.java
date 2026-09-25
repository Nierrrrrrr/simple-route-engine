package dev.routeengine.api;

import jakarta.servlet.http.HttpServletRequest;
import java.time.Instant;
import org.springframework.dao.DataAccessException;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.*;
import org.springframework.web.bind.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;
import jakarta.validation.ConstraintViolationException;

@RestControllerAdvice
public class ApiErrors {
 public record ErrorBody(String code,String message,String requestId,Instant timestamp){}
 public static ErrorBody body(String code,String message,String requestId){return new ErrorBody(code,message,requestId,Instant.now());}
 @ExceptionHandler(ApiProblem.class) ResponseEntity<ErrorBody> problem(ApiProblem p,HttpServletRequest r){return error(p.status(),p.code(),p.getMessage(),r);}
 @ExceptionHandler({MethodArgumentNotValidException.class,HttpMessageNotReadableException.class,ConstraintViolationException.class,MethodArgumentTypeMismatchException.class,MissingServletRequestParameterException.class})
 ResponseEntity<ErrorBody> invalid(Exception ignored,HttpServletRequest r){return error(422,"INVALID_REQUEST","Request does not match the supported schema",r);}
 @ExceptionHandler({NoHandlerFoundException.class,NoResourceFoundException.class,HttpRequestMethodNotSupportedException.class,HttpMediaTypeNotSupportedException.class,HttpMediaTypeNotAcceptableException.class})
 ResponseEntity<ErrorBody> clientHttp(Exception exception,HttpServletRequest request){return frameworkError((ErrorResponse)exception,request);}
 @ExceptionHandler({DataAccessException.class,org.springframework.transaction.TransactionException.class}) ResponseEntity<ErrorBody> database(Exception ignored,HttpServletRequest r){return error(503,"DATABASE_UNAVAILABLE","Database outcome unavailable; retain request identity",r);}
 @ExceptionHandler(Exception.class) ResponseEntity<ErrorBody> unexpected(Exception exception,HttpServletRequest r){
  if(exception instanceof ErrorResponse response && response.getStatusCode().is4xxClientError())return frameworkError(response,r);
  return error(500,"INTERNAL_ERROR","Request failed",r);
 }
 private ResponseEntity<ErrorBody> frameworkError(ErrorResponse response,HttpServletRequest request){
  String code=switch(response.getStatusCode().value()){
   case 404->"NOT_FOUND";
   case 405->"METHOD_NOT_ALLOWED";
   case 406->"NOT_ACCEPTABLE";
   case 415->"UNSUPPORTED_MEDIA_TYPE";
   default->"INVALID_REQUEST";
  };
  // Keep Allow/Accept and other framework headers, but never reflect exception payloads.
  return ResponseEntity.status(response.getStatusCode()).headers(response.getHeaders()).contentType(MediaType.APPLICATION_JSON)
    .body(body(code,"HTTP request is not supported",(String)request.getAttribute("requestId")));
 }
 private ResponseEntity<ErrorBody> error(int status,String code,String message,HttpServletRequest r){return ResponseEntity.status(status).contentType(MediaType.APPLICATION_JSON).body(body(code,message,(String)r.getAttribute("requestId")));}
}
